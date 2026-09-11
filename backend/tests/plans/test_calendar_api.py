"""Calendar creation through the logging GraphQL write paths."""

import datetime
from types import SimpleNamespace

import pytest
from django.apps import apps

from apps.exercises.models import DaySteps, Exercise
from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan
from config.schema import schema

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "kind, fields",
    [
        ("createIntake", 'meal: "lunch", numServings: 1'),
        ("createExercise", 'type: "walk", kcals: 100'),
        ("createDaySteps", "steps: 100"),
    ],
)
def test_id_logging_repairs_missing_sibling_days(db, week_plan, kind, fields):
    """Legacy ID-based forms still use the shared repair contract."""
    day = week_plan.days.get(day_num=1)
    week_plan.days.filter(day_num=4).delete()
    result = schema.execute_sync(
        f"mutation {{ {kind}(dayId: {day.pk}, {fields}) {{ id }} }}",
        context_value=SimpleNamespace(
            request=SimpleNamespace(user=week_plan.user)
        ),
    )
    assert result.errors is None
    assert week_plan.days.count() == 7


@pytest.mark.parametrize(
    "kind", ["createIntake", "createExercise", "createDaySteps"]
)
def test_failed_logging_rolls_back_calendar_creation(
    user, measurement_factory, week_plan_factory, mocker, kind
):
    """A downstream logging failure must roll back the newly ensured week."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    week_plan_factory(user=user, measurement=measurement)
    model, fields = {
        "createIntake": (Intake, 'meal: "lunch", numServings: 1'),
        "createExercise": (Exercise, 'type: "walk", kcals: 100'),
        "createDaySteps": (DaySteps, "steps: 100"),
    }[kind]
    mocker.patch.object(
        model, "save", side_effect=ValueError("injected logging failure")
    )
    result = schema.execute_sync(
        f'mutation {{ {kind}(dayDate: "2023-02-04", {fields}) {{ id }} }}',
        context_value=SimpleNamespace(request=SimpleNamespace(user=user)),
    )
    assert (
        result.errors
        and result.errors[0].message == "injected logging failure"
    )
    assert WeekPlan.objects.filter(user=user).count() == 1
    assert Day.objects.filter(plan__user=user).count() == 7


@pytest.mark.parametrize(
    "mutation",
    [
        'createIntake(dayDate: "2023-02-04", meal: "lunch", '
        "numServings: 1, energyKcal: 100)",
        'createExercise(dayDate: "2023-02-04", type: "walk", kcals: 100)',
        'createDaySteps(dayDate: "2023-02-04", steps: 100)',
    ],
)
def test_date_logging_creates_the_whole_week(
    user, measurement_factory, week_plan_factory, mutation
):
    """Logging never needs the caller to manufacture a day ID first."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    week_plan_factory(user=user, measurement=measurement)
    result = schema.execute_sync(
        "mutation { " + mutation + " { id } }",
        context_value=SimpleNamespace(request=SimpleNamespace(user=user)),
    )
    assert result.errors is None
    assert WeekPlan.objects.filter(user=user).count() == 2
    day = Day.objects.get(plan__user=user, day=datetime.date(2023, 2, 4))
    assert day.plan.days.count() == 7


@pytest.mark.parametrize(
    "kind, fields, model_name",
    [
        ("createIntake", 'meal: "lunch", numServings: 1', "Intake"),
        ("createExercise", 'type: "walk", kcals: 100', "Exercise"),
        ("createDaySteps", "steps: 100", "DaySteps"),
    ],
)
def test_id_logging_preserves_exact_overlapping_plan(
    week_plan, week_plan_factory, kind, fields, model_name
):
    """An explicit day ID remains authoritative even in legacy overlapping weeks."""
    day = week_plan.days.get(day_num=5)
    other = week_plan_factory(
        user=week_plan.user,
        measurement=week_plan.measurement,
        start_date=day.day,
    )
    week_plan.days.filter(day_num=4).delete()
    other.days.filter(day_num=4).delete()
    result = schema.execute_sync(
        f"mutation {{ {kind}(dayId: {day.pk}, {fields}) {{ id }} }}",
        context_value=SimpleNamespace(
            request=SimpleNamespace(user=week_plan.user)
        ),
    )
    assert result.errors is None
    model = apps.get_model(
        "plans" if model_name == "Intake" else "exercises", model_name
    )
    assert model.objects.get(pk=result.data[kind]["id"]).day_id == day.pk
    assert week_plan.days.count() == 7
    assert other.days.count() == 6


@pytest.mark.parametrize(
    "kind, fields",
    [
        ("createIntake", 'meal: "lunch", numServings: 1'),
        ("createExercise", 'type: "walk", kcals: 100'),
        ("createDaySteps", "steps: 100"),
    ],
)
@pytest.mark.parametrize(
    "selector",
    [
        "both",
        "neither",
        "foreign",
        "missing",
        "invalid_date",
        "anonymous_date",
        "anonymous_id",
    ],
)
def test_logging_rejects_invalid_selectors_without_calendar_writes(
    week_plan, user_factory, kind, fields, selector
):
    """Validate identity and authentication without repairing unauthorized calendars."""
    day = week_plan.days.get(day_num=1)
    week_plan.days.filter(day_num=4).delete()
    user = week_plan.user
    selectors = {
        "both": f'dayId: {day.pk}, dayDate: "{day.day}", ',
        "neither": "",
        "foreign": f"dayId: {day.pk}, ",
        "missing": "dayId: -1, ",
        "invalid_date": 'dayDate: "not-a-date", ',
        "anonymous_date": f'dayDate: "{day.day}", ',
        "anonymous_id": f"dayId: {day.pk}, ",
    }
    if selector == "foreign":
        user = user_factory()
    if selector.startswith("anonymous"):
        user = None
    before = (list(WeekPlan.objects.values()), list(Day.objects.values()))
    result = schema.execute_sync(
        f"mutation {{ {kind}({selectors[selector]}{fields}) {{ id }} }}",
        context_value=SimpleNamespace(request=SimpleNamespace(user=user)),
    )
    assert result.errors
    message = result.errors[0].message
    if selector in ("both", "neither"):
        assert message == "Provide exactly one of dayId or dayDate"
    elif selector in ("foreign", "missing"):
        assert message == "Day not found"
    elif selector.startswith("anonymous"):
        assert message == "Authentication required"
    else:
        assert "Invalid isoformat string" in message
    assert (
        list(WeekPlan.objects.values()),
        list(Day.objects.values()),
    ) == before
