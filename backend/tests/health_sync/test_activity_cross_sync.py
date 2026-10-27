"""Cross-upload activity ordering and overlap regressions."""

import datetime
import json
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.health_sync.models import ActivityImport, HealthSyncDevice
from apps.health_sync.services import (
    delete_manual_exercise,
    update_manual_exercise,
)


@pytest.fixture(autouse=True)
def isolated_upload_limits():
    """Keep real endpoint rate limits isolated from other test uploads."""
    cache.clear()
    yield
    cache.clear()


def record(**overrides):
    """Build a fixed session with independently versioned observations."""
    start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
    value = {
        "source_record_id": "session",
        "source_modified_at": (start - datetime.timedelta(days=1)).isoformat(),
        "observed_at": (
            timezone.now() - datetime.timedelta(hours=2)
        ).isoformat(),
        "start_time": start.isoformat(),
        "end_time": (start + datetime.timedelta(minutes=30)).isoformat(),
        "type": "run",
        "active_kcals": 300,
        "distance_km": None,
    }
    value.update(overrides)
    return value


def upload(client, token, *records):
    """Send a real independently acknowledged upload."""
    response = client.post(
        "/api/health-sync/activities/",
        data=json.dumps({"records": list(records)}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
def test_late_metrics_update_equal_session_version_and_reject_replays(
    client, user_factory, day_factory
):
    """Import delayed metrics without allowing old reads or sessions to win."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    first = record()
    later = {
        **first,
        "observed_at": timezone.now().isoformat(),
        "active_kcals": 450,
        "distance_km": 5.5,
    }
    assert upload(client, token, first)["summary"]["created"] == 1
    assert upload(client, token, later)["summary"]["updated"] == 1
    assert upload(client, token, first)["summary"]["unchanged"] == 1
    assert upload(client, token, later)["summary"]["unchanged"] == 1
    stale_session = {
        **later,
        "source_modified_at": (
            timezone.now() - datetime.timedelta(days=2)
        ).isoformat(),
        "observed_at": (
            timezone.now() + datetime.timedelta(minutes=1)
        ).isoformat(),
        "active_kcals": 1,
    }
    assert upload(client, token, stale_session)["summary"]["unchanged"] == 1
    exercise = Exercise.objects.get(day=day)
    assert (exercise.kcals, exercise.distance) == (450, Decimal("5.50"))
    assert (
        ActivityImport.objects.get().source_modified_at.isoformat()
        == first["source_modified_at"]
    )


@pytest.mark.django_db
@pytest.mark.parametrize("reverse", [False, True])
def test_first_accepted_overlap_wins_across_independent_uploads(
    client, user_factory, day_factory, reverse
):
    """Do not double count when later syncs choose a different envelope."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    nested = record()
    start = datetime.datetime.fromisoformat(nested["start_time"])
    enclosing = {
        **nested,
        "source_record_id": "enclosing",
        "start_time": (start - datetime.timedelta(minutes=15)).isoformat(),
        "end_time": (start + datetime.timedelta(minutes=45)).isoformat(),
        "active_kcals": 600,
    }
    first, second = (enclosing, nested) if reverse else (nested, enclosing)
    assert upload(client, token, first)["summary"]["created"] == 1
    assert upload(client, token, second)["summary"]["skipped"] == 1
    assert upload(client, token)["summary"]["created"] == 0
    assert Exercise.objects.get(day=day).kcals == first["active_kcals"]
    assert (
        ActivityImport.objects.get().source_record_id
        == first["source_record_id"]
    )


@pytest.mark.django_db
def test_legacy_interval_is_reserved_until_equal_version_replay_restores_it(
    client, user_factory, day_factory
):
    """Keep older stored rows safe without inventing their missing UTC offset."""
    user = user_factory()
    day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    original = record()
    original.pop("observed_at")
    upload(client, token, original)
    ActivityImport.objects.update(start_time=None, end_time=None)
    overlap = {**original, "source_record_id": "overlap"}
    assert upload(client, token, overlap)["summary"]["skipped"] == 1
    assert upload(client, token, original)["summary"]["unchanged"] == 1
    imported = ActivityImport.objects.get()
    assert imported.start_time == datetime.datetime.fromisoformat(
        original["start_time"]
    )
    assert imported.end_time == datetime.datetime.fromisoformat(
        original["end_time"]
    )
    assert imported.observed_at is None
    assert upload(client, token, overlap)["summary"]["skipped"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("delete", [False, True])
def test_manual_override_reserves_original_interval_and_ignores_observations(
    client, user_factory, day_factory, delete
):
    """Do not undo local edits/deletes through another envelope or observation."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    original = record()
    upload(client, token, original)
    exercise = Exercise.objects.get()
    if delete:
        delete_manual_exercise(user, exercise.pk)
    else:
        update_manual_exercise(
            user,
            exercise.pk,
            exercise_type="gym",
            kcals=99,
            time=datetime.time(20),
            duration=None,
            distance=None,
        )
    later = {
        **original,
        "observed_at": timezone.now().isoformat(),
        "active_kcals": 500,
    }
    assert upload(client, token, later)["summary"]["unchanged"] == 1
    assert (
        upload(client, token, {**later, "source_record_id": "replacement"})[
            "summary"
        ]["skipped"]
        == 1
    )
    imported = ActivityImport.objects.get()
    assert not imported.is_active
    assert imported.observed_at == datetime.datetime.fromisoformat(
        original["observed_at"]
    )
    assert imported.start_time == datetime.datetime.fromisoformat(
        original["start_time"]
    )
    if delete:
        assert not Exercise.objects.filter(day=day).exists()
    else:
        exercise.refresh_from_db()
        assert (exercise.kcals, exercise.time, exercise.duration) == (
            99,
            datetime.time(20),
            None,
        )


@pytest.mark.django_db
def test_chunk_boundaries_offsets_and_source_isolation(
    client, user_factory, day_factory
):
    """Reserve intervals per owner/source without deleting omitted records."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, device = HealthSyncDevice.issue(user, "Phone")
    first = record()
    start = datetime.datetime.fromisoformat(first["start_time"])
    other = Exercise.objects.create(day=day, type="walk", kcals=1)
    ActivityImport.objects.create(
        user=user,
        device=device,
        exercise=other,
        source="other_provider",
        source_record_id="other",
        source_modified_at=start,
        start_time=start,
        end_time=start + datetime.timedelta(hours=1),
    )
    manual = Exercise.objects.create(
        day=day, type="run", kcals=2, time=start.time()
    )
    assert upload(client, token, first)["summary"]["created"] == 1
    adjacent = {
        **first,
        "source_record_id": "adjacent",
        "start_time": first["end_time"],
        "end_time": (start + datetime.timedelta(hours=1)).isoformat(),
    }
    # A separate HTTP chunk has no authority to remove the first chunk's row.
    assert upload(client, token, adjacent)["summary"]["created"] == 1
    offset = datetime.timezone(datetime.timedelta(hours=2))
    equivalent = {
        **first,
        "source_record_id": "same-instant-other-offset",
        "start_time": start.astimezone(offset).isoformat(),
        "end_time": (start + datetime.timedelta(minutes=30))
        .astimezone(offset)
        .isoformat(),
    }
    assert upload(client, token, equivalent)["summary"]["skipped"] == 1
    other_user = user_factory()
    other_day = day_factory(plan__user=other_user, day=day.day)
    other_token, _device = HealthSyncDevice.issue(other_user, "Other phone")
    assert upload(client, other_token, first)["summary"]["created"] == 1
    assert Exercise.objects.filter(day=other_day).count() == 1
    assert Exercise.objects.filter(day=day).count() == 4
    assert Exercise.objects.filter(pk__in=[manual.pk, other.pk]).count() == 2
    assert upload(client, token)["summary"]["updated"] == 0
    assert Exercise.objects.filter(day=day).count() == 4


@pytest.mark.django_db
def test_interval_correction_cannot_overlap_another_reserved_session(
    client, user_factory, day_factory
):
    """Reject conflicting corrections atomically while allowing free interval moves."""
    user = user_factory()
    day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    first = record()
    start = datetime.datetime.fromisoformat(first["start_time"])
    second = {
        **first,
        "source_record_id": "second",
        "start_time": first["end_time"],
        "end_time": (start + datetime.timedelta(hours=1)).isoformat(),
    }
    upload(client, token, first, second)
    correction = {
        **first,
        "source_modified_at": timezone.now().isoformat(),
        "end_time": second["end_time"],
    }
    assert upload(client, token, correction)["summary"]["skipped"] == 1
    imported = ActivityImport.objects.get(source_record_id="session")
    assert imported.end_time == datetime.datetime.fromisoformat(
        first["end_time"]
    )
    correction.update(
        start_time=second["end_time"],
        end_time=(start + datetime.timedelta(hours=2)).isoformat(),
    )
    assert upload(client, token, correction)["summary"]["updated"] == 1
    assert upload(client, token, first)["summary"]["unchanged"] == 1
    assert Exercise.objects.count() == 2


@pytest.mark.django_db
def test_legacy_payload_keeps_strict_source_freshness_after_observed_upgrade(
    client, user_factory, day_factory
):
    """Old clients still create/update, but cannot bypass equal-version ordering."""
    user = user_factory()
    day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    legacy = record()
    legacy.pop("observed_at")
    upload(client, token, legacy)
    observed = {**legacy, "observed_at": timezone.now().isoformat()}
    assert upload(client, token, observed)["summary"]["unchanged"] == 1
    assert (
        ActivityImport.objects.get().observed_at
        == datetime.datetime.fromisoformat(observed["observed_at"])
    )
    assert (
        upload(client, token, {**legacy, "active_kcals": 1})["summary"][
            "unchanged"
        ]
        == 1
    )
    newer = {
        **legacy,
        "source_modified_at": timezone.now().isoformat(),
        "active_kcals": 500,
    }
    assert upload(client, token, newer)["summary"]["updated"] == 1
    assert ActivityImport.objects.get().observed_at is None
    assert upload(client, token, observed)["summary"]["unchanged"] == 1
    assert Exercise.objects.get().kcals == 500


@pytest.mark.django_db
@pytest.mark.parametrize(
    "observed",
    [None, "not-a-timestamp", "2026-01-01T12:00:00", "2099-01-01T12:00:00Z"],
)
def test_invalid_activity_observation_is_rejected_before_writes(
    client, user_factory, day_factory, observed
):
    """Validate optional observation timestamps before processing a batch."""
    user = user_factory()
    day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    response = client.post(
        "/api/health-sync/activities/",
        data=json.dumps(
            {
                "records": [
                    record(),
                    record(source_record_id="invalid", observed_at=observed),
                ]
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 400
    assert not Exercise.objects.exists()
    assert not ActivityImport.objects.exists()
