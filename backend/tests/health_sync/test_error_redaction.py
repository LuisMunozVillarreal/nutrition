"""Public health-sync errors must not reflect internal exception text."""

import datetime

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.exercises.models import DaySteps
from apps.health_sync.models import HealthSyncDevice, HealthSyncPairingCode
from tests.health_sync.test_api import post_json


@pytest.fixture(autouse=True)
def isolated_rate_limits():
    """Keep endpoint quotas independent of other tests on the worker."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["consume", "issue"])
def test_pairing_redacts_internal_value_errors(
    client, user_factory, mocker, operation
):
    """Reject internal failures without disclosing text or consuming a code."""
    user = user_factory()
    code, pairing = HealthSyncPairingCode.issue(user)
    model = (
        "HealthSyncPairingCode"
        if operation == "consume"
        else "HealthSyncDevice"
    )
    failure = mocker.patch(
        f"apps.health_sync.views.{model}.{operation}",
        side_effect=ValueError("private-internal-detail /srv/example.py"),
    )

    response = post_json(
        client,
        "/api/health-sync/pair/",
        {"code": code, "device_name": "Phone"},
    )

    failure.assert_called_once()
    assert response.status_code == 400
    assert b"private-internal-detail" not in response.content
    assert response.json() == {"error": "Invalid health-sync request"}
    pairing.refresh_from_db()
    assert pairing.consumed_at is None
    assert not HealthSyncDevice.objects.filter(user=user).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["_json_body", "parse_records"])
def test_upload_redacts_internal_value_errors(
    client, user_factory, mocker, operation
):
    """Unexpected parser messages cannot reach an authenticated companion."""
    token, device = HealthSyncDevice.issue(user_factory(), "Phone")
    failure = mocker.patch(
        f"apps.health_sync.views.{operation}",
        side_effect=ValueError("private-internal-detail /srv/example.py"),
    )
    sync = mocker.patch("apps.health_sync.views.sync_records")

    response = post_json(
        client, "/api/health-sync/steps/", {"records": []}, token
    )

    failure.assert_called_once()
    sync.assert_not_called()
    assert response.status_code == 400
    assert b"private-internal-detail" not in response.content
    assert response.json() == {"error": "Invalid health-sync request"}
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
def test_upload_redacts_real_datetime_parser_error(client, user_factory):
    """Malformed calendar timestamps do not disclose datetime internals."""
    token, device = HealthSyncDevice.issue(user_factory(), "Phone")
    response = post_json(
        client,
        "/api/health-sync/steps/",
        {
            "records": [
                {
                    "date": timezone.localdate().isoformat(),
                    "steps": 100,
                    "observed_at": "2026-13-01T12:00:00Z",
                }
            ]
        },
        token,
    )

    assert response.status_code == 400
    assert b"month must be in" not in response.content
    assert response.json() == {"error": "Invalid health-sync request"}
    assert not DaySteps.objects.exists()
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("shape", "records must be a list"),
        ("count", "records must contain at most 31 items"),
        ("record", "each record must be an object"),
        ("date", "date must use YYYY-MM-DD"),
        ("duplicate", "records must contain unique dates"),
        ("old", "date is outside the supported sync window"),
        ("future", "date cannot be in the future"),
        ("steps_type", "steps must be an integer"),
        ("steps_range", "steps must be between 0 and 1000000"),
        (
            "timestamp",
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
        ("future_timestamp", "observed_at cannot be in the future"),
    ],
)
def test_upload_preserves_public_validation_messages(
    client, user_factory, case, message
):
    """Real invalid payloads retain the documented actionable public copy."""
    token, _device = HealthSyncDevice.issue(user_factory(), "Phone")
    today = timezone.localdate()
    record = {
        "date": today.isoformat(),
        "steps": 100,
        "observed_at": timezone.now().isoformat(),
    }
    changes = {
        "date": {"date": "invalid"},
        "old": {"date": (today - datetime.timedelta(days=31)).isoformat()},
        "future": {"date": (today + datetime.timedelta(days=2)).isoformat()},
        "steps_type": {"steps": True},
        "steps_range": {"steps": -1},
        "timestamp": {"observed_at": "invalid"},
        "future_timestamp": {
            "observed_at": (
                timezone.now() + datetime.timedelta(hours=1)
            ).isoformat()
        },
    }
    record.update(changes.get(case, {}))
    payload = {
        "shape": {},
        "count": {"records": [record] * 32},
        "record": {"records": [None]},
        "duplicate": {"records": [record, record]},
    }.get(case, {"records": [record]})

    response = post_json(client, "/api/health-sync/steps/", payload, token)

    assert response.status_code == 400
    assert response.json() == {"error": message}
    assert not DaySteps.objects.exists()
