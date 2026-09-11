"""Real PostgreSQL contention tests for the on-demand calendar contract."""

import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connection, connections

from apps.measurements.models import Measurement
from apps.measurements.schema import MeasurementMutation
from apps.plans.models import Day, Intake, WeekPlan
from apps.plans.services import ensure_day, ensure_week_days


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="PostgreSQL row locks required"
)
@pytest.mark.parametrize(
    "scenario", ["new_same_date", "new_different_dates", "repair"]
)
def test_concurrent_ensure_and_logging(
    user, measurement_factory, week_plan_factory, scenario
):
    """Independent connections create one full week and retain both intakes."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    template = week_plan_factory(user=user, measurement=measurement)
    requested = datetime.date(2023, 2, 4)
    if scenario == "repair":
        requested = template.start_date
        template.days.filter(day_num__in=[1, 3, 7]).delete()
    ready = threading.Barrier(2)

    def log(offset):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid()")
                backend_pid = cursor.fetchone()[0]
            ready.wait(timeout=10)
            date = requested + datetime.timedelta(days=offset)
            day = ensure_day(user, date)
            Intake.objects.create(day=day, meal="lunch", energy_kcal=100)
            return backend_pid, day.pk, day.plan_id
        finally:
            connections.close_all()

    second_offset = 1 if scenario == "new_different_dates" else 0
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(log, 0)
        second = executor.submit(log, second_offset)
        results = [first.result(timeout=20), second.result(timeout=20)]
    assert results[0][0] != results[1][0]
    assert results[0][2] == results[1][2]
    if not second_offset:
        assert results[0][1] == results[1][1]
    plan = WeekPlan.objects.get(pk=results[0][2])
    assert plan.days.count() == 7
    assert Intake.objects.filter(day__plan=plan).count() == 2
    assert (
        sum(
            Day.objects.filter(plan=plan).values_list("energy_kcal", flat=True)
        )
        == 200
    )
    assert WeekPlan.objects.filter(user=user).count() == (
        1 if scenario == "repair" else 2
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="PostgreSQL row locks required"
)
@pytest.mark.parametrize("scenario", ["generate", "repair"])
def test_measurement_update_serializes_with_calendar(
    user, measurement_factory, week_plan_factory, scenario
):
    """A blocked measurement writer includes created days without an FK cycle."""
    # Explicit connection IDs and lock checkpoints keep this schedule red-capable.
    # pylint: disable=too-many-locals,too-many-statements
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    template = week_plan_factory(user=user, measurement=measurement)
    requested = template.start_date + datetime.timedelta(days=7)
    if scenario == "repair":
        template.days.filter(day_num=7).delete()
        requested = template.start_date
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

    def run_writer(calendar):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '12s'")
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            if calendar:
                with connection.execute_wrapper(checkpoint):
                    if scenario == "repair":
                        ensure_week_days(template)
                        return pid, template.pk
                    return pid, ensure_day(user, requested).plan_id
            updater_pids.put(pid)
            info = SimpleNamespace(
                context=SimpleNamespace(request=SimpleNamespace(user=user))
            )
            MeasurementMutation().update_measurement(
                info, id=str(measurement.pk), weight=90, body_fat_perc=21
            )
            return pid, None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        calendar_future = executor.submit(run_writer, True)
        try:
            assert plan_locked.wait(timeout=10)
            update_future = executor.submit(run_writer, False)
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
                assert (
                    time.monotonic() < deadline
                ), "Updater never waited on a lock"
                release_calendar.wait(timeout=0.01)
        finally:
            release_calendar.set()
        calendar_pid, plan_id = calendar_future.result(timeout=20)
        update_pid, _ = update_future.result(timeout=20)
    assert calendar_pid != update_pid
    assert calendar_pid in blockers
    plan = WeekPlan.objects.get(pk=plan_id)
    assert plan.days.count() == 7
    assert set(plan.days.values_list("protein_g_goal", flat=True)) == {
        template.protein_g_kg * Decimal("90")
    }
