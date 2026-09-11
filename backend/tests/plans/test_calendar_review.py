"""Regressions independently reproduced from calendar review findings."""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.measurements import schema as measurement_schema
from apps.measurements.models import Measurement
from apps.plans.models import WeekPlan
from apps.plans.schema import _validated_week_plan_parameters
from apps.plans.services import ensure_day, ensure_week_days

pytestmark = pytest.mark.django_db


def test_generated_week_revalidates_targets(
    user, measurement_factory, week_plan_factory
):
    """A newer measurement cannot turn copied targets into negative goals."""
    old = measurement_factory(
        user=user, weight=Decimal("94.3"), body_fat_perc=Decimal("21")
    )
    Measurement.objects.filter(pk=old.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    week_plan_factory(
        user=user,
        measurement=old,
        start_date=datetime.date(2023, 1, 9),
        protein_g_kg=Decimal("2"),
        fat_perc=Decimal("25"),
        deficit=700,
    )
    new = measurement_factory(
        user=user, weight=Decimal("50"), body_fat_perc=Decimal("21")
    )
    Measurement.objects.filter(pk=new.pk).update(
        created_at=datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc)
    )
    with pytest.raises(ValueError, match="carbsGGoal"):
        _validated_week_plan_parameters(new, 2, 25, 700)
    before = WeekPlan.objects.count()
    with pytest.raises(ValueError, match="carbsGGoal"):
        ensure_day(user, datetime.date(2023, 2, 6))
    assert WeekPlan.objects.count() == before


def test_measurement_update_includes_repaired_days(week_plan, mocker):
    """Repair before plan locking must not evade measurement recomputation."""
    week_plan.days.filter(day_num=7).delete()
    original = measurement_schema.lock_plan_aggregate_rows
    repaired = False

    def repair_then_lock(*args, **kwargs):
        nonlocal repaired
        if not repaired:
            repaired = True
            ensure_week_days(week_plan)
        return original(*args, **kwargs)

    mocker.patch.object(
        measurement_schema, "lock_plan_aggregate_rows", repair_then_lock
    )
    info = SimpleNamespace(
        context=SimpleNamespace(request=SimpleNamespace(user=week_plan.user))
    )
    measurement_schema.MeasurementMutation().update_measurement(
        info, id=str(week_plan.measurement_id), body_fat_perc=21, weight=90
    )
    values = list(week_plan.days.values_list("protein_g_goal", flat=True))
    assert len(values) == 7
    assert all(
        value == week_plan.protein_g_kg * Decimal("90") for value in values
    ), values
