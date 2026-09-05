"""Validation and device-management tests for health sync."""

import datetime
import json
import secrets
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from apps.exercises.admin import DayStepsInlineBase
from apps.exercises.models import DaySteps
from apps.health_sync import services as health_sync_services
from apps.health_sync.models import (
    HealthSyncDevice,
    HealthSyncPairingCode,
    StepImport,
    StepSyncWatermark,
)
from apps.health_sync.services import parse_records
from config.schema import schema


@pytest.fixture
def isolated_pair_rate_limit():
    """Keep cache-backed pairing quotas from leaking between tests."""
    cache.clear()
    yield
    cache.clear()


def bearer_context(user_id):
    """Build an authenticated bearer context."""
    token = jwt.encode(
        {"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256"
    )
    request = SimpleNamespace(
        META={"HTTP_AUTHORIZATION": f"Bearer {token}"},
        user=None,
    )
    return SimpleNamespace(request=request)


def session_context(user):
    """Build a GraphQL context resolved by app-level query mixins."""
    return SimpleNamespace(request=SimpleNamespace(user=user, META={}))


def test_kubernetes_routes_and_runtime_dependencies_are_declared():
    """The deployed public API reaches Django with shared rate-limit state."""
    repository = Path(__file__).resolve().parents[3]
    backend_manifest = (
        repository / "platform/k8s/base/backend.yaml"
    ).read_text()
    health_ingress_manifest = (
        repository / "platform/k8s/base/health-sync-ingress.yaml"
    ).read_text()
    base_kustomization = (
        repository / "platform/k8s/base/kustomization.yaml"
    ).read_text()

    assert "path: /api/health-sync" in health_ingress_manifest
    assert "maxRequestBodyBytes: 65536" in health_ingress_manifest
    assert "health-sync-body-limit@kubernetescrd" in health_ingress_manifest
    assert (
        "nutrition-staging-health-sync-body-limit"
        not in health_ingress_manifest
    )
    assert (
        "nutrition-production-health-sync-body-limit"
        not in health_ingress_manifest
    )
    assert "name: CACHE_URL" in backend_manifest
    assert "name: HEALTH_SYNC_TOKEN_PEPPER" in backend_manifest
    assert "name: HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS" in backend_manifest
    assert "redis.yaml" in base_kustomization

    redis_manifest = (repository / "platform/k8s/base/redis.yaml").read_text()
    assert "image: redis:7-alpine@sha256:" in redis_manifest
    assert "runAsUser: 999" in redis_manifest
    assert "runAsGroup: 1000" in redis_manifest

    backup_manifest = (
        repository / "platform/k8s/overlays/production/db-backup-cronjob.yaml"
    ).read_text()
    assert backup_manifest.count("name: SECRET_KEY") == 1
    assert backup_manifest.count("name: GEMINI_API_KEY") == 1


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "records must be a list"),
        ({"records": [None]}, "each record must be an object"),
        (
            {
                "records": [
                    {"date": "31-07-2026", "steps": 1, "observed_at": "x"}
                ]
            },
            "date must use YYYY-MM-DD",
        ),
        (
            {
                "records": [
                    {"date": "20260822", "steps": 1, "observed_at": "x"}
                ]
            },
            "date must use YYYY-MM-DD",
        ),
        (
            {
                "records": [
                    {"date": "2026-W34-6", "steps": 1, "observed_at": "x"}
                ]
            },
            "date must use YYYY-MM-DD",
        ),
        (
            {
                "records": [
                    {"date": "2026-99-99", "steps": 1, "observed_at": "x"}
                ]
            },
            "date must use YYYY-MM-DD",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": True,
                        "observed_at": "2026-07-31T12:00:00Z",
                    }
                ]
            },
            "steps must be an integer",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": -1,
                        "observed_at": "2026-07-31T12:00:00Z",
                    }
                ]
            },
            "steps must be between 0 and 1000000",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": 1,
                        "observed_at": "2026-07-31T12:00:00",
                    }
                ]
            },
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": 1,
                        "observed_at": 123456,
                    }
                ]
            },
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": 1,
                        "observed_at": None,
                    }
                ]
            },
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": 1,
                        "observed_at": True,
                    }
                ]
            },
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
        (
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": 1,
                        "observed_at": ["2026-07-31T12:00:00Z"],
                    }
                ]
            },
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
    ],
)
def test_parse_records_rejects_invalid_payloads(payload, message):
    """Invalid batches fail before any record can be written."""
    with pytest.raises(ValueError, match=message):
        parse_records(payload)


def test_parse_records_rejects_duplicate_dates_and_future_observations():
    """A batch has one authoritative sample per date and cannot come from the future."""
    observed = timezone.now().isoformat()
    duplicate = {
        "records": [
            {
                "date": timezone.localdate().isoformat(),
                "steps": 1,
                "observed_at": observed,
            },
            {
                "date": timezone.localdate().isoformat(),
                "steps": 2,
                "observed_at": observed,
            },
        ]
    }
    with pytest.raises(ValueError, match="unique dates"):
        parse_records(duplicate)

    future = {
        "records": [
            {
                "date": timezone.localdate().isoformat(),
                "steps": 1,
                "observed_at": (
                    timezone.now() + datetime.timedelta(minutes=6)
                ).isoformat(),
            }
        ]
    }
    with pytest.raises(ValueError, match="cannot be in the future"):
        parse_records(future)


def test_parse_records_allows_one_day_timezone_skew_but_not_two():
    """A phone east of UTC can legitimately be on the next calendar date."""
    observed = timezone.now().isoformat()
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    day_after_tomorrow = tomorrow + datetime.timedelta(days=1)

    assert (
        parse_records(
            {
                "records": [
                    {
                        "date": tomorrow.isoformat(),
                        "steps": 1,
                        "observed_at": observed,
                    }
                ]
            }
        )[0].date
        == tomorrow
    )

    with pytest.raises(ValueError, match="date cannot be in the future"):
        parse_records(
            {
                "records": [
                    {
                        "date": day_after_tomorrow.isoformat(),
                        "steps": 1,
                        "observed_at": observed,
                    }
                ]
            }
        )

    too_old = timezone.localdate() - datetime.timedelta(days=31)
    with pytest.raises(ValueError, match="outside the supported sync window"):
        parse_records(
            {
                "records": [
                    {
                        "date": too_old.isoformat(),
                        "steps": 1,
                        "observed_at": observed,
                    }
                ]
            }
        )


@pytest.mark.django_db
def test_sync_skips_noop_writes_when_steps_unchanged(
    client, user_factory, day_factory
):
    """A same-value upload advances the watermark without a no-op write."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    first = client.post(
        "/api/health-sync/steps/",
        data=json.dumps(
            {
                "records": [
                    {
                        "date": day.day.isoformat(),
                        "steps": 9000,
                        "observed_at": timezone.now().isoformat(),
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert first.status_code == 200
    day_steps = DaySteps.objects.get(day=day)
    updated_at_before = day_steps.updated_at

    replay = client.post(
        "/api/health-sync/steps/",
        data=json.dumps(
            {
                "records": [
                    {
                        "date": day.day.isoformat(),
                        "steps": 9000,
                        "observed_at": timezone.now().isoformat(),
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert replay.status_code == 200
    assert replay.json()["summary"]["unchanged"] == 1
    day_steps.refresh_from_db()
    assert day_steps.steps == 9000
    assert day_steps.updated_at == updated_at_before
    assert StepSyncWatermark.objects.filter(user=user, date=day.day).exists()


@pytest.mark.django_db
def test_device_query_and_revoke_are_owner_scoped(user_factory):
    """Users see and revoke only their own companion credentials."""
    owner = user_factory()
    other = user_factory()
    _owner_token, owner_device = HealthSyncDevice.issue(owner, "Owner phone")
    _other_token, other_device = HealthSyncDevice.issue(other, "Other phone")

    query = schema.execute_sync(
        "query { healthSyncDevices { id name } }",
        context_value=bearer_context(owner.id),
    )
    assert query.errors is None
    assert query.data == {
        "healthSyncDevices": [
            {"id": str(owner_device.id), "name": "Owner phone"}
        ]
    }

    cross_user = schema.execute_sync(
        f'mutation {{ revokeHealthSyncDevice(id: "{other_device.id}") }}',
        context_value=bearer_context(owner.id),
    )
    own = schema.execute_sync(
        f'mutation {{ revokeHealthSyncDevice(id: "{owner_device.id}") }}',
        context_value=bearer_context(owner.id),
    )
    assert cross_user.errors is None
    assert cross_user.data == {"revokeHealthSyncDevice": False}
    assert own.errors is None
    assert own.data == {"revokeHealthSyncDevice": True}
    owner_device.refresh_from_db()
    other_device.refresh_from_db()
    assert owner_device.revoked_at is not None
    assert other_device.revoked_at is None


@pytest.mark.django_db
def test_day_steps_query_exposes_import_provenance(
    user_factory,
    day_factory,
):
    """The UI can distinguish synced totals from manually entered totals."""
    user = user_factory()
    imported_day = day_factory(
        plan__user=user,
        day=timezone.localdate() - datetime.timedelta(days=1),
    )
    manual_day = day_factory(
        plan__user=user,
        day=timezone.localdate(),
    )
    imported_steps = DaySteps.objects.create(day=imported_day, steps=9000)
    DaySteps.objects.create(day=manual_day, steps=10000)
    _token, device = HealthSyncDevice.issue(user, "Phone")
    observed_at = timezone.now()
    StepImport.objects.create(
        day_steps=imported_steps,
        device=device,
        observed_at=observed_at,
    )

    result = schema.execute_sync(
        "query { dayStepsList { steps source syncedAt } }",
        context_value=session_context(user),
    )

    assert result.errors is None
    assert result.data == {
        "dayStepsList": [
            {"steps": 10000, "source": "manual", "syncedAt": None},
            {
                "steps": 9000,
                "source": "health_connect",
                "syncedAt": observed_at.isoformat(),
            },
        ]
    }


@pytest.mark.django_db
def test_manual_step_update_clears_import_provenance(
    client, user_factory, day_factory
):
    """A user override is labelled manual until a later device sync replaces it."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    day_steps = DaySteps.objects.create(day=day, steps=9000)
    token, device = HealthSyncDevice.issue(user, "Phone")
    observed_at = timezone.now()
    StepImport.objects.create(
        day_steps=day_steps,
        device=device,
        observed_at=observed_at,
    )
    StepSyncWatermark.objects.create(
        user=user,
        date=day.day,
        observed_at=observed_at,
    )

    result = schema.execute_sync(
        f"""
        mutation {{
          updateDaySteps(id: "{day_steps.id}", steps: 10000) {{ source steps }}
        }}
        """,
        context_value=session_context(user),
    )

    assert result.errors is None
    assert result.data == {
        "updateDaySteps": {"source": "manual", "steps": 10000}
    }
    watermark = StepImport.objects.get(day_steps=day_steps)
    assert watermark.is_active is False

    replay = client.post(
        "/api/health-sync/steps/",
        data=json.dumps(
            {
                "records": [
                    {
                        "date": day.day.isoformat(),
                        "steps": 9000,
                        "observed_at": observed_at.isoformat(),
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert replay.status_code == 200
    assert replay.json()["summary"]["unchanged"] == 1
    day_steps.refresh_from_db()
    watermark.refresh_from_db()
    assert day_steps.steps == 10000
    assert watermark.is_active is False


@pytest.mark.django_db
def test_manual_step_create_returns_stable_error_when_row_already_exists(
    user_factory, day_factory
):
    """A concurrent/existing manual total never escapes as an integrity 500."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    DaySteps.objects.create(day=day, steps=9000)

    result = schema.execute_sync(
        f"""
        mutation {{
          createDaySteps(dayId: {day.id}, steps: 10000) {{ id }}
        }}
        """,
        context_value=session_context(user),
    )

    assert result.errors
    assert result.errors[0].message == "Day steps already exist"
    assert DaySteps.objects.filter(day=day).count() == 1


@pytest.mark.django_db
def test_manual_step_create_returns_stable_error_when_day_disappears(
    user_factory, day_factory, monkeypatch
):
    """Concurrent day deletion cannot escape as a KeyError."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    original = health_sync_services.lock_plan_aggregate_rows

    def delete_then_lock(*args, **kwargs):
        type(day).objects.filter(pk=day.pk).delete()
        return original(*args, **kwargs)

    monkeypatch.setattr(
        health_sync_services,
        "lock_plan_aggregate_rows",
        delete_then_lock,
    )

    with pytest.raises(ValueError, match="Day not found"):
        health_sync_services.create_manual_day_steps(user, day.pk, 10000)


@pytest.mark.django_db
def test_manual_step_delete_uses_canonical_plan_locks(
    user_factory, day_factory, monkeypatch
):
    """Delete follows WeekPlan -> Day -> DaySteps before signals recalculate."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    day_steps = DaySteps.objects.create(day=day, steps=9000)
    calls = []
    original = health_sync_services.lock_plan_aggregate_rows

    def recording_lock(*args, **kwargs):
        calls.append(tuple(kwargs["day_ids"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(
        health_sync_services,
        "lock_plan_aggregate_rows",
        recording_lock,
    )
    result = schema.execute_sync(
        f'mutation {{ deleteDaySteps(id: "{day_steps.id}") }}',
        context_value=session_context(user),
    )

    assert result.errors is None
    assert result.data == {"deleteDaySteps": True}
    assert calls == [(day.id,)]
    assert not DaySteps.objects.filter(pk=day_steps.pk).exists()


@pytest.mark.django_db
def test_delete_and_recreate_preserves_stale_sync_watermark(
    client, user_factory, day_factory
):
    """Deleting and recreating manual steps cannot revive an old upload."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    day_steps = health_sync_services.create_manual_day_steps(
        user, day.pk, 9000
    )
    token, device = HealthSyncDevice.issue(user, "Phone")
    observed_at = timezone.now() - datetime.timedelta(minutes=5)
    first = client.post(
        "/api/health-sync/steps/",
        data=json.dumps(
            {
                "records": [
                    {
                        "date": day.day.isoformat(),
                        "steps": 9500,
                        "observed_at": observed_at.isoformat(),
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert first.status_code == 200

    health_sync_services.delete_manual_day_steps(user, day_steps.pk)
    recreated = health_sync_services.create_manual_day_steps(
        user, day.pk, 10000
    )
    replay = client.post(
        "/api/health-sync/steps/",
        data=json.dumps(
            {
                "records": [
                    {
                        "date": day.day.isoformat(),
                        "steps": 9500,
                        "observed_at": observed_at.isoformat(),
                    }
                ]
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert replay.status_code == 200
    assert replay.json()["summary"]["unchanged"] == 1
    recreated.refresh_from_db()
    assert recreated.steps == 10000
    assert StepImport.objects.filter(device=device).count() == 0


def test_admin_cannot_bypass_health_sync_locks_or_provenance():
    """Daily step writes remain available only through canonical services."""
    model_admin = admin.site._registry[DaySteps]
    assert model_admin.has_add_permission(None) is False
    assert model_admin.has_change_permission(None) is False
    assert model_admin.has_delete_permission(None) is False
    assert DayStepsInlineBase.readonly_fields == ["steps", "kcals"]
    assert DayStepsInlineBase.can_delete is False


@pytest.mark.django_db
def test_pair_and_upload_reject_malformed_or_oversized_json(
    client, user_factory
):
    """Companion endpoints bound parsing work and return stable client errors."""
    user = user_factory()
    token, _device = HealthSyncDevice.issue(user, "Phone")

    malformed = client.post(
        "/api/health-sync/pair/",
        data="{",
        content_type="application/json",
    )
    too_large = client.post(
        "/api/health-sync/steps/",
        data=json.dumps({"records": [], "padding": "x" * (65 * 1024)}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert malformed.status_code == 400
    assert malformed.json() == {"error": "Request body must be valid JSON"}
    assert too_large.status_code == 400
    assert too_large.json() == {"error": "Request body is too large"}


@pytest.mark.django_db
def test_pair_endpoint_rejects_excessively_nested_json(client):
    """A small but deeply nested public payload must not escape as a 500."""
    nested = "[" * 30_000 + "0" + "]" * 30_000

    response = client.post(
        "/api/health-sync/pair/",
        data=nested,
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Request body must be valid JSON"}


@pytest.mark.django_db
def test_pair_endpoint_rejects_excessive_json_integer(client):
    """JSON integer conversion limits become a stable client error, not a 500."""
    body = b'{"code":' + (b"9" * 5_000) + b',"device_name":"Phone"}'

    response = client.post(
        "/api/health-sync/pair/",
        data=body,
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Request body must be valid JSON"}


@pytest.mark.django_db
def test_pair_endpoint_rate_limits_repeated_guesses(
    client, isolated_pair_rate_limit
):
    """The public exchange endpoint bounds online pairing-code guesses."""
    responses = [
        client.post(
            "/api/health-sync/pair/",
            data=json.dumps({"code": "0" * 12, "device_name": "Phone"}),
            content_type="application/json",
        )
        for _attempt in range(21)
    ]

    assert all(response.status_code == 400 for response in responses[:20])
    assert responses[-1].status_code == 429
    assert responses[-1].json() == {"error": "Too many pairing attempts"}
    assert responses[-1]["Retry-After"] == "600"


@pytest.mark.django_db
@override_settings(
    HEALTH_SYNC_TRUSTED_PROXY_COUNT=1,
    HEALTH_SYNC_TRUSTED_PROXY_CIDRS=["127.0.0.0/8"],
)
def test_pair_rate_limit_uses_trusted_proxy_chain_for_client_identity(
    client, isolated_pair_rate_limit
):
    """A configured trusted proxy cannot collapse all clients into one quota."""
    for _attempt in range(20):
        response = client.post(
            "/api/health-sync/pair/",
            data=json.dumps({"code": "0" * 12, "device_name": "Phone"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="198.51.100.10",
        )
        assert response.status_code == 400

    other_client = client.post(
        "/api/health-sync/pair/",
        data=json.dumps({"code": "0" * 12, "device_name": "Phone"}),
        content_type="application/json",
        HTTP_X_FORWARDED_FOR="198.51.100.11",
    )
    assert other_client.status_code == 400


@pytest.mark.django_db
@override_settings(
    HEALTH_SYNC_TRUSTED_PROXY_COUNT=1,
    HEALTH_SYNC_TRUSTED_PROXY_CIDRS=["10.0.0.0/8"],
)
def test_untrusted_peer_cannot_spoof_forwarded_addresses(
    client, isolated_pair_rate_limit
):
    """Forwarded addresses are ignored unless the direct peer is trusted."""
    responses = [
        client.post(
            "/api/health-sync/pair/",
            data=json.dumps({"code": "0" * 12, "device_name": "Phone"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt}",
        )
        for attempt in range(1, 22)
    ]
    assert all(response.status_code == 400 for response in responses[:20])
    assert responses[-1].status_code == 429


@pytest.mark.django_db
@override_settings(HEALTH_SYNC_UPLOADS_PER_DEVICE=2)
def test_step_upload_rate_limits_each_device(client, user_factory):
    """A valid but abusive companion cannot issue unbounded uploads."""
    cache.clear()
    token, _device = HealthSyncDevice.issue(user_factory(), "Phone")
    responses = [
        client.post(
            "/api/health-sync/steps/",
            data=json.dumps({"records": []}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        for _attempt in range(3)
    ]
    cache.clear()
    assert [response.status_code for response in responses] == [200, 200, 429]


@pytest.mark.django_db
def test_authentication_checks_all_devices_with_a_colliding_prefix(
    user_factory, monkeypatch
):
    """A rare token-prefix collision must not invalidate a real credential."""
    suffixes = iter(("abcdefgh-first-token", "abcdefgh-second-token"))
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _size: next(suffixes))
    user = user_factory()
    _first_token, _first = HealthSyncDevice.issue(user, "First")
    second_token, second = HealthSyncDevice.issue(user, "Second")

    assert HealthSyncDevice.authenticate(second_token) == second


@pytest.mark.django_db
def test_pairing_code_collision_retries_inside_an_outer_transaction(
    user_factory, monkeypatch
):
    """A numeric-code collision does not poison the emission transaction."""
    values = iter((123, 123, 456))
    monkeypatch.setattr(secrets, "randbelow", lambda _limit: next(values))
    first_user = user_factory()
    second_user = user_factory()
    first_code, _first = HealthSyncPairingCode.issue(first_user)

    with transaction.atomic():
        second_code, pairing = HealthSyncPairingCode.issue(second_user)

    assert first_code == "000000000123"
    assert second_code == "000000000456"
    assert pairing.user == second_user


@pytest.mark.django_db
def test_expired_device_token_is_rejected(user_factory):
    """A stolen device credential cannot remain valid indefinitely."""
    user = user_factory()
    token, device = HealthSyncDevice.issue(user, "Phone")
    device.expires_at = timezone.now() - datetime.timedelta(seconds=1)
    device.save(update_fields=["expires_at"])

    assert HealthSyncDevice.authenticate(token) is None
    result = schema.execute_sync(
        "query { healthSyncDevices { id } }",
        context_value=bearer_context(user.id),
    )
    assert result.errors is None
    assert result.data == {"healthSyncDevices": []}


@pytest.mark.django_db
def test_device_issuance_caps_active_rows_and_prunes_expired_devices(
    user_factory,
):
    """One account cannot accumulate an unbounded active device list."""
    user = user_factory()
    devices = [
        HealthSyncDevice.issue(user, f"Phone {index}")[1]
        for index in range(10)
    ]

    with pytest.raises(
        ValueError, match="Too many active health-sync devices"
    ):
        HealthSyncDevice.issue(user, "Overflow")

    expired = devices[0]
    expired.expires_at = timezone.now() - datetime.timedelta(seconds=1)
    expired.save(update_fields=["expires_at"])
    HealthSyncDevice.issue(user, "Replacement")

    assert not HealthSyncDevice.objects.filter(pk=expired.pk).exists()
    assert (
        HealthSyncDevice.objects.filter(user=user, revoked_at=None).count()
        == 10
    )


@pytest.mark.django_db
def test_token_pepper_fallback_rehashes_a_device_after_rotation(user_factory):
    """Rotating the dedicated pepper preserves and upgrades active devices."""
    user = user_factory()
    with override_settings(
        HEALTH_SYNC_TOKEN_PEPPER="old-pepper",
        HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS=[],
    ):
        token, device = HealthSyncDevice.issue(user, "Phone")
        old_hash = device.token_hash

    with override_settings(
        HEALTH_SYNC_TOKEN_PEPPER="new-pepper",
        HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS=["old-pepper"],
    ):
        assert HealthSyncDevice.authenticate(token) == device

    device.refresh_from_db()
    assert device.token_hash != old_hash


@pytest.mark.django_db
def test_sync_revalidates_target_after_overlapping_day_appears(
    user_factory, day_factory, monkeypatch
):
    """A date that becomes ambiguous while locking is skipped, never guessed."""
    user = user_factory()
    target_date = timezone.localdate()
    day_factory(plan__user=user, day=target_date)
    _token, device = HealthSyncDevice.issue(user, "Phone")
    original = health_sync_services.lock_plan_aggregate_rows

    def add_overlap_then_lock(*args, **kwargs):
        locks = original(*args, **kwargs)
        day_factory(plan__user=user, day=target_date)
        return locks

    monkeypatch.setattr(
        health_sync_services,
        "lock_plan_aggregate_rows",
        add_overlap_then_lock,
    )
    result = health_sync_services.sync_records(
        device,
        parse_records(
            {
                "records": [
                    {
                        "date": target_date.isoformat(),
                        "steps": 123,
                        "observed_at": timezone.now().isoformat(),
                    }
                ]
            }
        ),
    )

    assert result["summary"]["skipped"] == 1
    assert DaySteps.objects.count() == 0


@pytest.mark.django_db
def test_sync_skips_target_deleted_before_aggregate_lock(
    user_factory, day_factory, monkeypatch
):
    """A concurrently deleted target becomes a stable skipped result."""
    user = user_factory()
    target_date = timezone.localdate()
    day = day_factory(plan__user=user, day=target_date)
    _token, device = HealthSyncDevice.issue(user, "Phone")
    original = health_sync_services.lock_plan_aggregate_rows

    def delete_then_lock(*args, **kwargs):
        DaySteps.objects.filter(day=day).delete()
        type(day).objects.filter(pk=day.pk).delete()
        return original(*args, **kwargs)

    monkeypatch.setattr(
        health_sync_services,
        "lock_plan_aggregate_rows",
        delete_then_lock,
    )
    result = health_sync_services.sync_records(
        device,
        parse_records(
            {
                "records": [
                    {
                        "date": target_date.isoformat(),
                        "steps": 123,
                        "observed_at": timezone.now().isoformat(),
                    }
                ]
            }
        ),
    )

    assert result["summary"]["skipped"] == 1
