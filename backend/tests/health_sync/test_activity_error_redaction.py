"""Activity upload errors expose only fixed public validation messages."""

import datetime

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.health_sync.models import ActivityImport, HealthSyncDevice
from tests.health_sync.test_activity_api import _record, _upload, post_json


@pytest.fixture(autouse=True)
def isolated_rate_limits():
    """Keep endpoint quotas independent of other tests on the worker."""
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["_json_body", "parse_activity_records"])
def test_activity_upload_redacts_internal_value_errors(
    client, user_factory, mocker, operation
):
    """Unexpected parser details never reach the companion or trigger writes."""
    token, device = HealthSyncDevice.issue(user_factory(), "Phone")
    failure = mocker.patch(
        f"apps.health_sync.views.{operation}",
        side_effect=ValueError("private-internal-detail /srv/example.py"),
    )
    sync = mocker.patch("apps.health_sync.views.sync_activity_records")

    response = _upload(client, token)

    failure.assert_called_once()
    sync.assert_not_called()
    assert response.status_code == 400
    assert b"private-internal-detail" not in response.content
    assert response.json() == {"error": "Invalid health-sync request"}
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field", ["source_modified_at", "observed_at", "start_time", "end_time"]
)
def test_activity_upload_redacts_real_datetime_parser_errors(
    client, user_factory, field
):
    """Invalid calendar timestamps do not disclose datetime implementation text."""
    token, device = HealthSyncDevice.issue(user_factory(), "Phone")

    response = _upload(
        client, token, _record(**{field: "2026-13-01T12:00:00Z"})
    )

    assert response.status_code == 400
    assert b"month must be in" not in response.content
    assert response.json() == {"error": "Invalid health-sync request"}
    assert not Exercise.objects.exists()
    assert not ActivityImport.objects.exists()
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("shape", "records must be a list"),
        ("count", "records must contain at most 100 items"),
        ("record", "each record must be an object"),
        (
            "source_record_id",
            "source_record_id must be a string of 1 to 255 characters",
        ),
        ("duplicate", "records must contain unique source_record_id values"),
        (
            "source_modified_at",
            "source_modified_at must be an ISO-8601 timestamp with timezone",
        ),
        (
            "future_modified",
            "source_modified_at cannot be in the future",
        ),
        (
            "observed_at",
            "observed_at must be an ISO-8601 timestamp with timezone",
        ),
        ("future_observed", "observed_at cannot be in the future"),
        (
            "start_time",
            "start_time must be an ISO-8601 timestamp with timezone",
        ),
        (
            "end_time",
            "end_time must be an ISO-8601 timestamp with timezone",
        ),
        ("order", "start_time must be before end_time"),
        ("duration", "duration must not exceed 24 hours"),
        ("future_activity", "activity cannot be in the future"),
        ("type", "type must be one of: walk, run, cycle, gym"),
        ("active_kcals", "active_kcals must be an integer"),
        ("kcals_range", "active_kcals must be between 0 and 100000"),
        ("distance_km", "distance_km must be a finite number"),
        (
            "negative_distance",
            "distance_km must be greater than or equal to 0",
        ),
        (
            "large_distance",
            "distance_km must be less than or equal to 99999999.99",
        ),
    ],
)
def test_activity_upload_preserves_public_validation_messages(
    client, user_factory, case, message
):
    """Real invalid activity payloads retain their actionable public errors."""
    token, device = HealthSyncDevice.issue(user_factory(), "Phone")
    now = timezone.now()
    future = now + datetime.timedelta(days=3)
    changes = {
        "source_record_id": {"source_record_id": ""},
        "source_modified_at": {"source_modified_at": "invalid"},
        "future_modified": {"source_modified_at": future.isoformat()},
        "observed_at": {"observed_at": "invalid"},
        "future_observed": {"observed_at": future.isoformat()},
        "start_time": {"start_time": "invalid"},
        "end_time": {"end_time": "invalid"},
        "order": {"start_time": now.isoformat()},
        "duration": {
            "start_time": (now - datetime.timedelta(hours=25)).isoformat()
        },
        "future_activity": {
            "start_time": future.isoformat(),
            "end_time": (future + datetime.timedelta(hours=1)).isoformat(),
        },
        "type": {"type": "invalid"},
        "active_kcals": {"active_kcals": True},
        "kcals_range": {"active_kcals": -1},
        "distance_km": {"distance_km": "invalid"},
        "negative_distance": {"distance_km": -1},
        "large_distance": {"distance_km": 100000000},
    }
    record = _record(**changes.get(case, {}))
    payload = {
        "shape": {},
        "count": {"records": [{}] * 101},
        "record": {"records": [None]},
        "duplicate": {"records": [record, record]},
    }.get(case, {"records": [record]})

    response = post_json(
        client, "/api/health-sync/activities/", payload, token
    )

    assert response.status_code == 400
    assert response.json() == {"error": message}
    assert not Exercise.objects.exists()
    assert not ActivityImport.objects.exists()
    device.refresh_from_db()
    assert device.last_success_at is None
