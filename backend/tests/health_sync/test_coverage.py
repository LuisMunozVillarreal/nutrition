"""Residual branch coverage for Health Connect synchronization."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.exercises.models import DaySteps
from apps.health_sync import services, views
from apps.health_sync.models import HealthSyncPairingCode
from apps.health_sync.schema import HealthSyncQuery


def _production_probe_env(**overrides: str) -> dict[str, str]:
    """Build an isolated production settings environment."""
    coverage_config = Path(__file__).resolve().parents[2] / "pyproject.toml"
    return {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "ENVIRONMENT": "production",
        "ALLOWED_HOSTS": "example.com",
        "SECRET_KEY": "settings-probe-secret-with-enough-entropy",
        "GEMINI_API_KEY": "local-test-key",
        "DATABASE_URL": "sqlite:///tmp/nutrition-health-settings.sqlite3",
        "COVERAGE_PROCESS_START": str(coverage_config),
        **overrides,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"CACHE_URL": "redis://localhost:6379/1"},
            "HEALTH_SYNC_TOKEN_PEPPER must be independent from SECRET_KEY",
        ),
        (
            {"HEALTH_SYNC_TOKEN_PEPPER": "independent-health-pepper"},
            "Production health-sync rate limits require a shared CACHE_URL",
        ),
    ],
)
def test_production_health_sync_settings_fail_closed(overrides, message):
    """Production rejects shared secrets and process-local rate limits."""
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        env=_production_probe_env(**overrides),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert message in result.stderr


def test_preview_settings_allow_local_rate_limit_cache_before_manifest_merge():
    """A staging preview can boot from trusted main manifests during a PR."""
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        env=_production_probe_env(ENVIRONMENT="staging"),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "cache_url", ["dummycache://", "filecache:///tmp/cache"]
)
def test_production_rejects_non_distributed_cache_backends(cache_url):
    """Production rate limiting accepts only an approved shared cache."""
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        env=_production_probe_env(
            HEALTH_SYNC_TOKEN_PEPPER="independent-health-pepper",
            CACHE_URL=cache_url,
        ),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1
    assert "shared CACHE_URL" in result.stderr


@pytest.mark.django_db
def test_pairing_code_issue_exhausts_collision_retries(
    user_factory, monkeypatch
):
    """Persistent code collisions fail explicitly after the bounded retries."""
    first_user = user_factory()
    second_user = user_factory()
    monkeypatch.setattr("secrets.randbelow", lambda _limit: 123)
    HealthSyncPairingCode.issue(first_user)

    with pytest.raises(RuntimeError, match="Could not generate a unique"):
        HealthSyncPairingCode.issue(second_user)


def test_health_sync_query_rejects_unauthenticated_context():
    """The device-management GraphQL surface requires authentication."""
    info = SimpleNamespace(
        context=SimpleNamespace(
            request=SimpleNamespace(
                user=SimpleNamespace(is_authenticated=False), META={}
            )
        )
    )

    with pytest.raises(PermissionError, match="Authentication required"):
        HealthSyncQuery().health_sync_devices(info)


def test_parse_records_rejects_more_than_the_batch_limit():
    """A companion cannot exceed the bounded upload batch."""
    with pytest.raises(ValueError, match="at most 31"):
        services.parse_records({"records": [{}] * 32})


def test_zero_steps_have_zero_calories():
    """A zero-step daily aggregate has no derived calorie burn."""
    assert DaySteps(steps=0).kcals == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("service_name", "missing_line"),
    [
        ("update_manual_day_steps", "locked-day"),
        ("delete_manual_day_steps", "locked-day"),
        ("update_manual_day_steps", "deleted-row"),
        ("delete_manual_day_steps", "deleted-row"),
    ],
)
def test_manual_step_services_fail_closed_when_locked_rows_disappear(
    service_name,
    missing_line,
    user_factory,
    day_factory,
    mocker,
):
    """Concurrent disappearance produces the stable owner-scoped error."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    day_steps = DaySteps.objects.create(day=day, steps=10)
    locks = SimpleNamespace(
        days_by_pk={} if missing_line == "locked-day" else {day.pk: day},
        clear_markers=mocker.Mock(),
    )
    mocker.patch(
        "apps.health_sync.services.lock_plan_aggregate_rows",
        return_value=locks,
    )
    if missing_line == "deleted-row":
        locked_queryset = mocker.MagicMock()
        locked_queryset.using.return_value.get.side_effect = (
            DaySteps.DoesNotExist
        )
        mocker.patch(
            "apps.health_sync.services.DaySteps.objects.select_for_update",
            return_value=locked_queryset,
        )

    service = getattr(services, service_name)
    args = (
        (user, day_steps.pk, 20)
        if service_name.startswith("update")
        else (
            user,
            day_steps.pk,
        )
    )
    with pytest.raises(ValueError, match="Day steps not found"):
        service(*args)
    locks.clear_markers.assert_called_once_with()


def test_rate_counter_recovers_from_an_invalid_cached_value(mocker):
    """A corrupted cache counter is reset instead of escaping as a 500."""
    mocker.patch.object(views.cache, "add", return_value=False)
    mocker.patch.object(views.cache, "incr", side_effect=ValueError)
    reset = mocker.patch.object(views.cache, "set")

    assert views._increment_rate_limit("key", 1, 60) is False
    reset.assert_called_once_with("key", 1, timeout=60)


@override_settings(
    HEALTH_SYNC_TRUSTED_PROXY_COUNT=1,
    HEALTH_SYNC_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"],
)
def test_client_address_ignores_invalid_peer_and_forwarded_values():
    """Malformed network metadata cannot become a trusted client identity."""
    invalid_peer = SimpleNamespace(
        META={"REMOTE_ADDR": "invalid", "HTTP_X_FORWARDED_FOR": "198.51.100.1"}
    )
    assert views._client_address(invalid_peer) == "invalid"

    invalid_forwarded = SimpleNamespace(
        META={"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "invalid"}
    )
    assert views._client_address(invalid_forwarded) == "10.0.0.5"


@override_settings(
    HEALTH_SYNC_TRUSTED_PROXY_COUNT=1,
    HEALTH_SYNC_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"],
)
def test_client_address_trusts_ipv4_mapped_proxy_peer():
    """Dual-stack proxy addresses retain the configured IPv4 trust boundary."""
    request = SimpleNamespace(
        META={
            "REMOTE_ADDR": "::ffff:10.0.0.5",
            "HTTP_X_FORWARDED_FOR": "198.51.100.1",
        }
    )

    assert views._client_address(request) == "198.51.100.1"


def test_json_body_accepts_body_with_malformed_content_length():
    """A malformed Content-Length falls back to the bounded read."""
    request = SimpleNamespace(
        META={"CONTENT_LENGTH": "invalid"}, read=lambda size: b"{}"
    )
    assert views._json_body(request) == {}


def test_json_body_rejects_declared_oversized_content_length():
    """A declared body larger than the contract is rejected before reading."""
    request = SimpleNamespace(
        META={"CONTENT_LENGTH": str(64 * 1024 + 1)},
        read=lambda size: b"{}",
    )
    with pytest.raises(ValueError, match="too large"):
        views._json_body(request)


def test_json_body_rejects_oversized_body_with_understated_content_length():
    """A bounded read rejects oversized bodies even when length is understated."""
    request = SimpleNamespace(
        META={"CONTENT_LENGTH": "1"},
        read=lambda size: b"x" * (64 * 1024 + 1),
    )
    with pytest.raises(ValueError, match="too large"):
        views._json_body(request)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "Request body must be a JSON object"),
        ({"code": "invalid", "device_name": "Phone"}, "invalid or expired"),
        ({"code": "0" * 12, "device_name": ""}, "1 to 120 characters"),
    ],
)
def test_pair_endpoint_rejects_invalid_shapes(client, payload, message):
    """Pairing validation returns stable client errors for each public branch."""
    response = client.post(
        "/api/health-sync/pair/",
        data=__import__("json").dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert message in response.json()["error"]


@pytest.mark.django_db
def test_upload_ip_rate_limit_returns_retry_after(client, mocker):
    """The pre-authentication upload quota returns a bounded retry response."""
    mocker.patch(
        "apps.health_sync.views._upload_ip_rate_limited", return_value=True
    )

    response = client.post(
        "/api/health-sync/steps/",
        data='{"records": []}',
        content_type="application/json",
    )

    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert response.json() == {"error": "Too many upload attempts"}
