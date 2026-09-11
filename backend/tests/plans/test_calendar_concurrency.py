"""Real PostgreSQL contention tests for the on-demand calendar contract."""

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection, connections

from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan
from apps.plans.services import ensure_day


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
