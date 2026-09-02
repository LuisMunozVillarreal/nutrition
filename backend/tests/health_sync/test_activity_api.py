"""Activity upload endpoint acceptance and manual-override tests."""

import datetime
import json
from types import SimpleNamespace

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.health_sync.models import ActivityImport, HealthSyncDevice
from apps.health_sync.services import (
    delete_manual_exercise,
    parse_activity_records,
    sync_activity_records,
    update_manual_exercise,
)
from config.schema import schema


def bearer_context(user_id):
    """Build an authenticated GraphQL context for a user."""
    token = jwt.encode(
        {"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256"
    )
    request = SimpleNamespace(
        META={"HTTP_AUTHORIZATION": f"Bearer {token}"},
        user=None,
    )
    return SimpleNamespace(request=request)


def session_context(user):
    """Build a session-based GraphQL context for exercise mutations."""
    return SimpleNamespace(request=SimpleNamespace(user=user, META={}))


def post_json(client, path, payload, token=None):
    """POST JSON to a health-sync endpoint."""
    headers = {}
    if token is not None:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


def _record(source_record_id="garmin-1", **overrides):
    """Build an activity record whose session lands on today's local date."""
    now = timezone.now()
    start = now - datetime.timedelta(hours=1)
    end = start + datetime.timedelta(minutes=30)
    record = {
        "source_record_id": source_record_id,
        "source_modified_at": now.isoformat(),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "type": "walk",
        "active_kcals": 300,
        "distance_km": 5.25,
    }
    record.update(overrides)
    return record


def _upload(client, token, *records):
    return post_json(
        client,
        "/api/health-sync/activities/",
        {"records": list(records)},
        token,
    )


@pytest.mark.django_db
def test_activity_upload_requires_a_valid_scoped_device_token(client):
    """Verify activity synchronization behavior."""
    missing = post_json(
        client, "/api/health-sync/activities/", {"records": []}
    )
    invalid = post_json(
        client,
        "/api/health-sync/activities/",
        {"records": []},
        "not-a-token",
    )
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json() == {"error": "Authentication required"}


@pytest.mark.django_db
def test_activity_upload_rejects_oversized_body(client, user_factory):
    """Verify activity synchronization behavior."""
    user = user_factory()
    token, _device = HealthSyncDevice.issue(user, "Phone")
    response = post_json(
        client,
        "/api/health-sync/activities/",
        {"records": [], "padding": "x" * (65 * 1024)},
        token,
    )
    assert response.status_code == 400
    assert response.json() == {"error": "Request body is too large"}


@pytest.mark.django_db
def test_activity_upload_ip_rate_limit_returns_retry_after(client, mocker):
    """Verify activity synchronization behavior."""
    mocker.patch(
        "apps.health_sync.views._upload_ip_rate_limited", return_value=True
    )
    response = post_json(
        client, "/api/health-sync/activities/", {"records": []}
    )
    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert response.json() == {"error": "Too many upload attempts"}


@pytest.mark.django_db
def test_activity_upload_device_rate_limit_returns_retry_after(
    client, user_factory, mocker
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    token, _device = HealthSyncDevice.issue(user, "Phone")
    mocker.patch(
        "apps.health_sync.views._device_upload_rate_limited", return_value=True
    )
    response = _upload(client, token)
    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    assert response.json() == {"error": "Too many upload attempts"}


@pytest.mark.django_db
def test_activity_upload_creates_exercise_and_import_idempotently(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, device = HealthSyncDevice.issue(user, "Phone")

    record = _record()
    first = _upload(client, token, record)
    assert first.status_code == 200
    assert first.json()["summary"] == {
        "created": 1,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
    }

    exercise = Exercise.objects.get(day=day)
    assert exercise.type == "walk"
    assert exercise.kcals == 300
    assert exercise.distance is not None
    imported = ActivityImport.objects.get(exercise=exercise)
    assert imported.user == user
    assert imported.device == device
    assert imported.source == "garmin_health_connect"
    assert imported.source_record_id == "garmin-1"
    assert imported.is_active is True

    replay = _upload(client, token, record)
    assert replay.json()["summary"]["unchanged"] == 1
    assert Exercise.objects.filter(day=day).count() == 1
    assert ActivityImport.objects.filter(user=user).count() == 1
    device.refresh_from_db()
    assert device.last_success_at is not None


@pytest.mark.django_db
def test_stale_activity_upload_cannot_overwrite_a_newer_activity(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    newer = timezone.now()
    older = newer - datetime.timedelta(hours=1)

    for kcals, modified in ((500, newer), (100, older)):
        response = _upload(
            client,
            token,
            _record(
                active_kcals=kcals, source_modified_at=modified.isoformat()
            ),
        )
        assert response.status_code == 200

    assert Exercise.objects.get(day=day).kcals == 500


@pytest.mark.django_db
def test_newer_source_timestamp_with_same_values_advances_provenance(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    original_modified = timezone.now()
    original_record = _record(source_modified_at=original_modified.isoformat())
    _upload(client, token, original_record)
    newer_modified = original_modified + datetime.timedelta(minutes=1)

    response = _upload(
        client,
        token,
        {**original_record, "source_modified_at": newer_modified.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["unchanged"] == 1
    imported = ActivityImport.objects.get(
        user=user, source_record_id="garmin-1"
    )
    assert imported.source_modified_at == newer_modified
    assert Exercise.objects.count() == 1


@pytest.mark.django_db
def test_newer_activity_modification_updates_exercise(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")

    _upload(client, token, _record())
    newer = timezone.now() + datetime.timedelta(minutes=1)
    response = _upload(
        client,
        token,
        _record(
            active_kcals=800, type="run", source_modified_at=newer.isoformat()
        ),
    )

    assert response.json()["summary"]["updated"] == 1
    exercise = Exercise.objects.get(day=day)
    assert exercise.kcals == 800
    assert exercise.type == "run"


@pytest.mark.django_db
def test_newer_activity_date_change_moves_exercise_without_leaving_duplicate(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    today = timezone.localdate()
    tomorrow = today + datetime.timedelta(days=1)
    old_day = day_factory(plan__user=user, day=today)
    new_day = day_factory(plan=old_day.plan, day=tomorrow)
    token, _device = HealthSyncDevice.issue(user, "Phone")
    original_modified = timezone.now()

    _upload(
        client,
        token,
        _record(source_modified_at=original_modified.isoformat()),
    )
    start = datetime.datetime.combine(
        tomorrow,
        datetime.time(9, 0),
        tzinfo=datetime.timezone.utc,
    )
    response = _upload(
        client,
        token,
        _record(
            source_modified_at=(
                original_modified + datetime.timedelta(minutes=1)
            ).isoformat(),
            start_time=start.isoformat(),
            end_time=(start + datetime.timedelta(minutes=30)).isoformat(),
        ),
    )

    assert response.status_code == 200
    assert response.json()["summary"]["updated"] == 1
    assert Exercise.objects.count() == 1
    assert Exercise.objects.get().day == new_day
    assert not Exercise.objects.filter(day=old_day).exists()


@pytest.mark.django_db
def test_activity_upload_skips_missing_or_ambiguous_days(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    owner = user_factory()
    other = user_factory()
    day_factory(
        plan__user=other, day=timezone.localdate() - datetime.timedelta(days=1)
    )
    day_factory(plan__user=owner, day=timezone.localdate())
    day_factory(plan__user=owner, day=timezone.localdate())
    token, device = HealthSyncDevice.issue(owner, "Phone")

    response = _upload(client, token, _record())
    assert response.status_code == 200
    assert response.json()["summary"]["skipped"] == 1
    assert Exercise.objects.count() == 0
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
def test_activity_upload_does_not_attach_to_another_users_day(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    owner = user_factory()
    other = user_factory()
    owner_day = day_factory(plan__user=owner, day=timezone.localdate())
    other_day = day_factory(plan__user=other, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(owner, "Phone")

    response = _upload(client, token, _record())
    assert response.status_code == 200
    assert response.json()["summary"]["created"] == 1
    assert Exercise.objects.filter(day=owner_day).count() == 1
    assert Exercise.objects.filter(day=other_day).count() == 0


@pytest.mark.django_db
def test_empty_upload_does_not_advance_device_success_timestamp(
    client, user_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    token, device = HealthSyncDevice.issue(user, "Phone")
    response = _upload(client, token)
    assert response.status_code == 200
    assert response.json()["summary"] == {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
    }
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
def test_manual_update_deactivates_import_and_stale_replay_is_ignored(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    original_modified = timezone.now()
    _upload(
        client,
        token,
        _record(source_modified_at=original_modified.isoformat()),
    )
    exercise = Exercise.objects.get(day=day)

    result = schema.execute_sync(
        f"""
        mutation {{
          updateExercise(id: "{exercise.id}", type: "gym", kcals: 999) {{
            id type kcals
          }}
        }}
        """,
        context_value=session_context(user),
    )
    assert result.errors is None
    imported = ActivityImport.objects.get(
        user=user, source_record_id="garmin-1"
    )
    assert imported.is_active is False

    stale = _upload(
        client,
        token,
        _record(source_modified_at=original_modified.isoformat()),
    )
    assert stale.json()["summary"]["unchanged"] == 1
    exercise.refresh_from_db()
    assert (exercise.type, exercise.kcals) == ("gym", 999)

    newer = _upload(
        client,
        token,
        _record(
            active_kcals=700,
            source_modified_at=(
                original_modified + datetime.timedelta(minutes=5)
            ).isoformat(),
        ),
    )
    assert newer.json()["summary"]["updated"] == 1
    exercise.refresh_from_db()
    imported.refresh_from_db()
    assert (exercise.type, exercise.kcals) == ("walk", 700)
    assert imported.is_active is True


@pytest.mark.django_db
def test_manual_delete_detaches_import_and_newer_upload_recreates(
    client, user_factory, day_factory
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    original_modified = timezone.now()
    _upload(
        client,
        token,
        _record(source_modified_at=original_modified.isoformat()),
    )
    exercise = Exercise.objects.get(day=day)

    result = schema.execute_sync(
        f'mutation {{ deleteExercise(id: "{exercise.id}") }}',
        context_value=session_context(user),
    )
    assert result.errors is None
    assert result.data == {"deleteExercise": True}
    assert not Exercise.objects.filter(pk=exercise.id).exists()
    imported = ActivityImport.objects.get(
        user=user, source_record_id="garmin-1"
    )
    assert imported.exercise_id is None
    assert imported.is_active is False

    stale = _upload(
        client,
        token,
        _record(source_modified_at=original_modified.isoformat()),
    )
    assert stale.json()["summary"]["unchanged"] == 1
    assert Exercise.objects.filter(day=day).count() == 0

    newer = _upload(
        client,
        token,
        _record(
            source_modified_at=(
                original_modified + datetime.timedelta(minutes=5)
            ).isoformat(),
        ),
    )
    assert newer.json()["summary"]["created"] == 1
    assert Exercise.objects.filter(day=day).count() == 1
    imported.refresh_from_db()
    assert imported.is_active is True
    assert imported.exercise_id is not None


@pytest.mark.django_db
def test_activity_sync_skips_if_target_day_changes_after_lock_planning(
    user_factory, day_factory, mocker
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    _token, device = HealthSyncDevice.issue(user, "Phone")
    records = parse_activity_records({"records": [_record()]})
    values_list = mocker.patch(
        "apps.health_sync.services.Day.objects"
    ).using.return_value.filter.return_value.values_list
    values_list.side_effect = [[day.pk], []]
    fake_locks = SimpleNamespace(
        days_by_pk={day.pk: day},
        clear_markers=mocker.MagicMock(),
    )
    mocker.patch(
        "apps.health_sync.services.lock_plan_owner",
        return_value=user,
    )
    mocker.patch(
        "apps.health_sync.services.lock_plan_aggregate_rows",
        return_value=fake_locks,
    )

    result = sync_activity_records(device, records)

    assert result["summary"]["skipped"] == 1
    assert result["records"] == [
        {"source_record_id": "garmin-1", "status": "skipped"}
    ]
    fake_locks.clear_markers.assert_called_once()


def _update_manually(user, exercise_id):
    return update_manual_exercise(
        user,
        exercise_id,
        exercise_type="walk",
        kcals=10,
        time=datetime.time(9),
        duration=None,
        distance=None,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "operation", [_update_manually, delete_manual_exercise]
)
def test_manual_exercise_operation_rejects_unknown_id(user_factory, operation):
    """Verify activity synchronization behavior."""
    user = user_factory()

    with pytest.raises(ValueError, match="Exercise not found"):
        operation(user, 999999)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "operation", [_update_manually, delete_manual_exercise]
)
def test_manual_exercise_operation_rejects_day_removed_before_lock(
    user_factory, day_factory, operation, mocker
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    exercise = Exercise.objects.create(day=day, type="walk", kcals=10)
    fake_locks = SimpleNamespace(
        days_by_pk={},
        clear_markers=mocker.MagicMock(),
    )
    mocker.patch(
        "apps.health_sync.services.lock_plan_aggregate_rows",
        return_value=fake_locks,
    )

    with pytest.raises(ValueError, match="Exercise not found"):
        operation(user, exercise.pk)

    fake_locks.clear_markers.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "operation", [_update_manually, delete_manual_exercise]
)
def test_manual_exercise_operation_rejects_row_removed_after_day_lock(
    user_factory, day_factory, operation, mocker
):
    """Verify activity synchronization behavior."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    exercise = Exercise.objects.create(day=day, type="walk", kcals=10)
    fake_locks = SimpleNamespace(
        days_by_pk={day.pk: day},
        clear_markers=mocker.MagicMock(),
    )
    mocker.patch(
        "apps.health_sync.services.lock_plan_aggregate_rows",
        return_value=fake_locks,
    )
    locked_query = mocker.patch(
        "apps.health_sync.services.Exercise.objects.select_for_update"
    ).return_value.using.return_value
    locked_query.get.side_effect = Exercise.DoesNotExist

    with pytest.raises(ValueError, match="Exercise not found"):
        operation(user, exercise.pk)

    fake_locks.clear_markers.assert_called_once()
