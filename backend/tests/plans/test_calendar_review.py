"""Regressions independently reproduced from calendar review findings."""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.exercises.models import DaySteps
from apps.measurements import schema as measurement_schema
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from apps.plans.schema import _validated_week_plan_parameters
from apps.plans.services import ensure_day, ensure_week_days
from config.schema import schema

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("selector", ["id", "date"])
@pytest.mark.parametrize("missing", [[4, 5, 6, 7], [2, 4, 5, 6, 7]])
def test_repair_rejects_invalid_missing_goals_atomically(
    measurement_factory, week_plan_factory, selector, missing, mocker
):
    """Valid survivors cannot license negative goals on missing siblings."""
    measurement = measurement_factory(
        weight=Decimal("94.3"), body_fat_perc=Decimal("21")
    )
    user = measurement.user
    plan = week_plan_factory(
        user=user,
        measurement=measurement,
        protein_g_kg=Decimal("2"),
        fat_perc=Decimal("25"),
        deficit=700,
    )
    assert all(
        goal > 0 for goal in plan.days.values_list("carbs_g_goal", flat=True)
    )
    plan.days.filter(day_num__in=missing).delete()
    context = SimpleNamespace(request=SimpleNamespace(user=user))
    measurement_schema.MeasurementMutation().update_measurement(
        SimpleNamespace(context=context),
        id=str(measurement.pk),
        weight=50,
        body_fat_perc=21,
    )
    assert all(
        goal > 0 for goal in plan.days.values_list("carbs_g_goal", flat=True)
    )
    before = list(plan.days.order_by("pk").values())
    plan_before = WeekPlan.objects.filter(pk=plan.pk).get()
    day = plan.days.get(day_num=1)
    argument = (
        f"dayId: {day.pk}" if selector == "id" else f'dayDate: "{day.day}"'
    )
    saves = mocker.spy(Day, "save")
    result = schema.execute_sync(
        f"mutation {{ createDaySteps({argument}, steps: 100) {{ id }} }}",
        context_value=context,
    )
    assert result.errors and result.errors[0].message == (
        "carbsGGoal must be greater than or equal to 0"
    )
    saves.assert_not_called()
    assert list(plan.days.order_by("pk").values()) == before
    plan.refresh_from_db()
    assert plan.updated_at == plan_before.updated_at
    assert not DaySteps.objects.filter(day__plan=plan).exists()


@pytest.mark.parametrize("missing", [[], [2]])
def test_repair_validates_only_missing_days_with_default_tracking(
    user, measurement_factory, week_plan_factory, missing
):
    """Preserve estimated survivors when only a low-deficit tracked day is absent."""
    measurement = measurement_factory(
        user=user, weight=Decimal("94.3"), body_fat_perc=Decimal("21")
    )
    plan = week_plan_factory(
        user=user,
        measurement=measurement,
        protein_g_kg=Decimal("2"),
        fat_perc=Decimal("25"),
        deficit=700,
    )
    plan.days.update(tracked=False)
    info = SimpleNamespace(
        context=SimpleNamespace(request=SimpleNamespace(user=user))
    )
    measurement_schema.MeasurementMutation().update_measurement(
        info,
        id=str(measurement.pk),
        weight=50,
        body_fat_perc=21,
    )
    plan.days.filter(day_num__in=missing).delete()
    survivors = list(plan.days.order_by("pk").values())
    ensure_week_days(plan)
    assert plan.days.count() == 7
    assert (
        list(plan.days.exclude(day_num__in=missing).order_by("pk").values())
        == survivors
    )
    if missing:
        repaired = plan.days.get(day_num=2)
        assert repaired.tracked is True
        assert repaired.deficit == 560
        assert repaired.carbs_g_goal > 0


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
