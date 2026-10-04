"""Date-based Health Connect calendar creation acceptance tests."""

import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connection, connections
from django.utils import timezone

from apps.exercises.models import DaySteps
from apps.health_sync import services
from apps.health_sync.models import (
    HealthSyncDevice,
    StepImport,
    StepSyncWatermark,
)
from apps.measurements.models import Measurement
from apps.measurements.schema import MeasurementMutation
from apps.plans.models import Day, WeekPlan
from apps.plans.services import ensure_day
from tests.health_sync.test_api import post_json


@pytest.fixture
def calendar_template(user, measurement_factory, week_plan_factory):
    """Create established targets with an eligible historical measurement."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=30)
    )
    return week_plan_factory(
        user=user,
        measurement=measurement,
        start_date=timezone.localdate() - datetime.timedelta(days=7),
    )


def upload(client, user, date):
    """Upload a dated aggregate through the existing authenticated endpoint."""
    token, device = HealthSyncDevice.issue(user=user, name="Calendar test")
    payload = {
        "records": [
            {
                "date": date.isoformat(),
                "steps": 1234,
                "observed_at": timezone.now().isoformat(),
            }
        ]
    }
    return post_json(client, "/api/health-sync/steps/", payload, token), device


@pytest.mark.django_db
def test_upload_creates_complete_calendar_week(client, calendar_template):
    """A missing date initializes its anchored week before storing steps."""
    requested = timezone.localdate()
    response, device = upload(client, calendar_template.user, requested)
    assert response.status_code == 200
    assert response.json()["summary"]["created"] == 1
    day = Day.objects.get(plan__user=calendar_template.user, day=requested)
    assert day.plan.start_date == requested
    assert day.plan.days.count() == 7
    assert day.plan.measurement_id == calendar_template.measurement_id
    assert day.plan.protein_g_kg == calendar_template.protein_g_kg
    assert day.plan.fat_perc == calendar_template.fat_perc
    assert day.plan.deficit == calendar_template.deficit
    assert DaySteps.objects.get(day=day).steps == 1234
    assert StepImport.objects.get(day_steps__day=day).device == device
    assert WeekPlan.objects.filter(user=calendar_template.user).count() == 2
    before = list(day.plan.days.order_by("pk").values())
    watermark = StepSyncWatermark.objects.get(user=device.user, date=requested)
    replay = services.sync_records(
        device,
        [services.DailyStepRecord(requested, 1234, watermark.observed_at)],
    )
    assert replay["summary"]["unchanged"] == 1
    assert list(day.plan.days.order_by("pk").values()) == before
    assert StepImport.objects.count() == DaySteps.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("prerequisite", ["plan", "measurement"])
def test_missing_prerequisites_remain_retryable(
    client, user, calendar_template, prerequisite
):
    """Missing history skips the date without inventing targets or physiology."""
    if prerequisite == "plan":
        calendar_template.delete()
    else:
        Measurement.objects.filter(pk=calendar_template.measurement_id).update(
            created_at=timezone.now() + datetime.timedelta(days=1)
        )
    before = (WeekPlan.objects.count(), Day.objects.count())
    response, device = upload(client, user, timezone.localdate())
    assert response.status_code == 200
    assert response.json()["records"] == [
        {
            "date": timezone.localdate().isoformat(),
            "status": "skipped",
            "reason": "missing_plan_day",
        }
    ]
    assert (WeekPlan.objects.count(), Day.objects.count()) == before
    assert not DaySteps.objects.exists()
    assert not StepImport.objects.exists()
    assert not StepSyncWatermark.objects.exists()
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
def test_calendar_rejection_rolls_back_before_skipping(
    client, calendar_template, mocker
):
    """A calendar failure cannot leave generated rows or disclose its details."""

    def fail_after_generation(user, date):
        ensure_day(user, date)
        raise ValueError("private-calendar-detail /srv/example.py")

    mocker.patch(
        "apps.health_sync.services.ensure_day",
        side_effect=fail_after_generation,
    )
    before = (WeekPlan.objects.count(), Day.objects.count())
    response, _ = upload(client, calendar_template.user, timezone.localdate())
    assert response.json()["records"][0]["reason"] == "missing_plan_day"
    assert "private-calendar-detail" not in response.content.decode()
    assert (WeekPlan.objects.count(), Day.objects.count()) == before
    assert not DaySteps.objects.exists()
    assert not StepImport.objects.exists()


@pytest.mark.django_db
def test_repair_preserves_survivors_and_manual_provenance(
    client, calendar_template
):
    """Missing target repair never resaves other days or marks manual steps."""
    survivor = calendar_template.days.get(day_num=1)
    manual = DaySteps.objects.create(day=survivor, steps=99)
    missing = calendar_template.days.get(day_num=3)
    requested = missing.day
    missing.delete()
    before = list(calendar_template.days.order_by("pk").values())
    response, _ = upload(client, calendar_template.user, requested)
    assert response.json()["summary"]["created"] == 1
    assert calendar_template.days.count() == 7
    assert (
        list(
            calendar_template.days.exclude(day=requested)
            .order_by("pk")
            .values()
        )
        == before
    )
    manual.refresh_from_db()
    assert manual.steps == 99
    assert not StepImport.objects.filter(day_steps=manual).exists()


@pytest.mark.django_db
def test_existing_day_does_not_generate_calendar(
    client, calendar_template, mocker
):
    """Existing targets keep their settings and do not initialize siblings."""
    calendar_template.days.filter(day_num=3).delete()
    ensure = mocker.patch("apps.health_sync.services.ensure_day")
    response, _ = upload(
        client, calendar_template.user, calendar_template.start_date
    )
    assert response.json()["summary"]["created"] == 1
    assert calendar_template.days.count() == 6
    ensure.assert_not_called()


@pytest.mark.django_db
def test_import_failure_rolls_back_new_calendar(
    client, calendar_template, mocker
):
    """Calendar, steps, provenance and watermark share the record transaction."""
    mocker.patch.object(
        StepImport, "save", side_effect=RuntimeError("write failed")
    )
    before = (WeekPlan.objects.count(), Day.objects.count())
    with pytest.raises(RuntimeError, match="write failed"):
        upload(client, calendar_template.user, timezone.localdate())
    assert (WeekPlan.objects.count(), Day.objects.count()) == before
    assert not DaySteps.objects.exists()
    assert not StepImport.objects.exists()
    assert not StepSyncWatermark.objects.exists()


@pytest.mark.django_db
def test_owner_lock_precedes_calendar_and_import_locks(
    client, calendar_template, mocker
):
    """The shared resolver runs inside the owner-locked record transaction."""
    owner_lock = mocker.spy(services, "lock_plan_owner")
    aggregate_lock = mocker.spy(services, "lock_plan_aggregate_rows")

    def resolve(user, date):
        assert connection.in_atomic_block
        assert owner_lock.call_count == 1
        assert aggregate_lock.call_count == 0
        return ensure_day(user, date)

    resolver = mocker.patch.object(services, "ensure_day", side_effect=resolve)
    response, _ = upload(client, calendar_template.user, timezone.localdate())
    assert response.json()["summary"]["created"] == 1
    resolver.assert_called_once()


@pytest.mark.django_db
@pytest.mark.parametrize("offset", [-31, 2])
def test_out_of_window_upload_never_creates_calendar(
    client, calendar_template, offset
):
    """The existing ingestion bounds reject dates before any calendar writes."""
    before = (WeekPlan.objects.count(), Day.objects.count())
    response, _ = upload(
        client,
        calendar_template.user,
        timezone.localdate() + datetime.timedelta(days=offset),
    )
    assert response.status_code == 400
    assert (WeekPlan.objects.count(), Day.objects.count()) == before


@pytest.mark.django_db
def test_unauthenticated_upload_never_creates_calendar(
    client, calendar_template
):
    """No calendar is created before the scoped token has been authenticated."""
    before = (WeekPlan.objects.count(), Day.objects.count())
    response = post_json(
        client,
        "/api/health-sync/steps/",
        {
            "records": [
                {
                    "date": timezone.localdate().isoformat(),
                    "steps": 1234,
                    "observed_at": timezone.now().isoformat(),
                }
            ]
        },
    )
    assert response.status_code == 401
    assert (WeekPlan.objects.count(), Day.objects.count()) == before


@pytest.mark.django_db
def test_overlap_rejection_does_not_stop_later_records(
    calendar_template, week_plan_factory
):
    """Whole-window overlap validation skips only the unresolved date."""
    requested = timezone.localdate()
    week_plan_factory(
        user=calendar_template.user,
        measurement=calendar_template.measurement,
        start_date=requested + datetime.timedelta(days=1),
    )
    _, device = HealthSyncDevice.issue(
        user=calendar_template.user, name="test"
    )
    before = (WeekPlan.objects.count(), Day.objects.count())
    result = services.sync_records(
        device,
        [
            services.DailyStepRecord(requested, 1234, timezone.now()),
            services.DailyStepRecord(
                calendar_template.start_date, 4321, timezone.now()
            ),
        ],
    )
    assert result["records"][0]["reason"] == "missing_plan_day"
    assert result["records"][1]["status"] == "created"
    assert (WeekPlan.objects.count(), Day.objects.count()) == before
    assert DaySteps.objects.get().steps == 4321


@pytest.mark.django_db
def test_missing_plan_retry_succeeds_after_user_sets_targets(
    client, user, measurement_factory, week_plan_factory
):
    """An initial skip leaves no watermark that could prevent a later retry."""
    response, device = upload(client, user, timezone.localdate())
    assert response.json()["summary"]["skipped"] == 1
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=30)
    )
    week_plan_factory(
        user=user,
        measurement=measurement,
        start_date=timezone.localdate() - datetime.timedelta(days=7),
    )
    result = services.sync_records(
        device,
        [services.DailyStepRecord(timezone.localdate(), 1234, timezone.now())],
    )
    assert result["summary"]["created"] == 1
    assert WeekPlan.objects.filter(user=user).count() == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="PostgreSQL row locks required"
)
def test_concurrent_sync_creates_one_calendar_and_import(calendar_template):
    """Distinct sync connections serialize before creating the absent week."""
    _, device = HealthSyncDevice.issue(
        user=calendar_template.user, name="test"
    )
    requested = timezone.localdate()
    record = services.DailyStepRecord(requested, 1234, timezone.now())
    ready = threading.Barrier(2)

    def sync():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            ready.wait(timeout=10)
            return pid, services.sync_records(device, [record])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(sync)
        second = executor.submit(sync)
        results = [first.result(timeout=20), second.result(timeout=20)]
    assert results[0][0] != results[1][0]
    assert sorted(result[1]["records"][0]["status"] for result in results) == [
        "created",
        "unchanged",
    ]
    assert WeekPlan.objects.filter(user=device.user).count() == 2
    day = Day.objects.get(plan__user=device.user, day=requested)
    assert day.plan.days.count() == 7
    assert DaySteps.objects.get(day=day).steps == 1234
    assert StepImport.objects.count() == StepSyncWatermark.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="PostgreSQL row locks required"
)
@pytest.mark.parametrize("repair", [False, True])
def test_measurement_update_serializes_with_sync(calendar_template, repair):
    """The measurement writer waits without a deferred-FK deadlock or stale days."""
    # Separate backend IDs and evaluated SQL checkpoints force real contention.
    # pylint: disable=too-many-locals,too-many-statements
    _, device = HealthSyncDevice.issue(
        user=calendar_template.user, name="test"
    )
    requested = timezone.localdate()
    if repair:
        missing = calendar_template.days.get(day_num=3)
        requested = missing.day
        missing.delete()
    record = services.DailyStepRecord(requested, 1234, timezone.now())
    plan_locked = threading.Event()
    release_calendar = threading.Event()
    updater_pids = Queue()

    def checkpoint(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if (
            '"plans_weekplan"' in sql
            and "FOR UPDATE" in sql
            and not plan_locked.is_set()
        ):
            plan_locked.set()
            assert release_calendar.wait(timeout=10)
        return result

    def write(sync):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            if sync:
                with connection.execute_wrapper(checkpoint):
                    result = services.sync_records(device, [record])
                    assert result["summary"]["created"] == 1
                return pid
            updater_pids.put(pid)
            info = SimpleNamespace(
                context=SimpleNamespace(
                    request=SimpleNamespace(user=calendar_template.user)
                )
            )
            MeasurementMutation().update_measurement(
                info,
                id=str(calendar_template.measurement_id),
                weight=90,
                body_fat_perc=21,
            )
            return pid
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        sync_future = executor.submit(write, True)
        try:
            assert plan_locked.wait(timeout=10)
            update_future = executor.submit(write, False)
            updater_pid = updater_pids.get(timeout=10)
            deadline = time.monotonic() + 5
            while True:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_blocking_pids(%s)", [updater_pid]
                    )
                    blockers = cursor.fetchone()[0]
                if blockers:
                    break
                assert time.monotonic() < deadline, "Updater never waited"
                release_calendar.wait(timeout=0.01)
        finally:
            release_calendar.set()
        sync_pid = sync_future.result(timeout=20)
        update_pid = update_future.result(timeout=20)
    assert sync_pid != update_pid
    assert sync_pid in blockers
    day = Day.objects.get(plan__user=device.user, day=requested)
    assert day.plan.days.count() == 7
    assert set(day.plan.days.values_list("protein_g_goal", flat=True)) == {
        calendar_template.protein_g_kg * Decimal("90")
    }
    assert DaySteps.objects.get(day=day).steps == 1234
