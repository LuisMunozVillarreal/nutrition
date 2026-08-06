"""Focused branch coverage for plan GraphQL resolvers."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan
from apps.plans.schema import (
    DayType,
    PlanMutation,
    PlanQuery,
    WeekPlanType,
    _day_tdee,
    _validated_week_plan_parameters,
)


def _info(user):
    """Build the request context shape consumed by GraphQL helpers."""
    return SimpleNamespace(
        context=SimpleNamespace(request=SimpleNamespace(user=user)),
        selected_fields=[],
    )


def _authenticated_user():
    """Return a minimal authenticated principal for direct resolver tests."""
    return SimpleNamespace(is_authenticated=True)


@pytest.mark.parametrize("user", [None, AnonymousUser()])
def test_plan_queries_return_empty_results_for_unauthenticated_callers(user):
    """Every plan query fails closed for missing and anonymous users."""
    query = PlanQuery()
    info = _info(user)

    assert query.week_plans(info) == []
    assert query.week_plan(info, "1") is None
    assert query.day(info, "1") is None
    assert query.intake(info, "1") is None


@pytest.mark.parametrize(
    ("resolver", "model", "owner_filter"),
    [
        ("week_plan", WeekPlan, "user"),
        ("day", Day, "plan__user"),
        ("intake", Intake, "day__plan__user"),
    ],
)
def test_plan_queries_return_none_when_owned_object_is_missing(
    mocker, resolver, model, owner_filter
):
    """Owned-object lookups translate model absence into nullable results."""
    user = _authenticated_user()
    queryset_mock = mocker.Mock()
    queryset_mock.get.side_effect = model.DoesNotExist
    filter_mock = mocker.patch.object(
        model.objects, "filter", return_value=queryset_mock
    )
    get_mock = mocker.patch.object(
        model.objects, "get", side_effect=model.DoesNotExist
    )

    result = getattr(PlanQuery(), resolver)(_info(user), "404")

    assert result is None
    if resolver == "week_plan":
        filter_mock.assert_called_once_with(pk="404", user=user)
        queryset_mock.get.assert_called_once_with()
    elif resolver == "day":
        filter_mock.assert_called_once_with(plan__user=user)
        queryset_mock.get.assert_called_once_with(pk="404")
    else:
        get_mock.assert_called_once_with(pk="404", day__plan__user=user)


@pytest.mark.parametrize(
    ("resolver", "model", "graphql_type", "owner_filter"),
    [
        (
            "week_plan",
            WeekPlan,
            "apps.plans.schema.WeekPlanType",
            "user",
        ),
        (
            "intake",
            Intake,
            "apps.plans.schema.IntakeType",
            "day__plan__user",
        ),
    ],
)
def test_plan_queries_convert_found_owned_objects(
    mocker, resolver, model, graphql_type, owner_filter
):
    """Owned-object query success paths delegate to their GraphQL wrappers."""
    obj = mocker.Mock()
    converted = mocker.Mock()
    converter = mocker.patch(
        f"{graphql_type}.from_model", return_value=converted
    )
    user = _authenticated_user()
    queryset_mock = mocker.Mock()
    queryset_mock.get.return_value = obj
    filter_mock = mocker.patch.object(
        model.objects, "filter", return_value=queryset_mock
    )
    get_mock = mocker.patch.object(model.objects, "get", return_value=obj)

    result = getattr(PlanQuery(), resolver)(_info(user), "1")

    assert result is converted
    if resolver == "week_plan":
        filter_mock.assert_called_once_with(pk="1", user=user)
        queryset_mock.get.assert_called_once_with()
    else:
        get_mock.assert_called_once_with(pk="1", day__plan__user=user)
    converter.assert_called_once_with(obj)


def test_day_type_orders_and_converts_intakes(mocker):
    """The day wrapper returns ordered intake GraphQL values."""
    intake = SimpleNamespace(
        id=1,
        day_id=2,
        food_id=None,
        num_servings=Decimal("1.5"),
        meal="lunch",
        meal_order=2,
        energy_kcal=Decimal("100"),
        protein_g=Decimal("10"),
        fat_g=Decimal("3"),
        carbs_g=Decimal("15"),
    )
    queryset = mocker.Mock()
    queryset.order_by.return_value = [intake]
    filter_mock = mocker.patch.object(
        Intake.objects, "filter", return_value=queryset
    )
    day = SimpleNamespace(id=2, model=None)

    result = DayType.intakes(day)

    filter_mock.assert_called_once_with(day_id=2)
    queryset.order_by.assert_called_once_with("meal_order", "created_at")
    assert [str(item.id) for item in result] == ["1"]


def test_day_tdee_untracked_uses_bmr_rate():
    """Untracked days resolve TDEE straight from the plan BMR."""
    day = SimpleNamespace(
        tracked=False,
        plan=SimpleNamespace(
            measurement=SimpleNamespace(bmr=Decimal("2000")),
            EXERCISE_RATE=Decimal("1.375"),
        ),
    )

    assert _day_tdee(day) == (Decimal("2000") * Decimal("1.375")).normalize()


def test_day_tdee_falls_back_to_eat_when_unannotated():
    """Days without the batched eat_total annotation use the plain sum."""
    day = SimpleNamespace(
        tracked=True,
        steps=SimpleNamespace(kcals=Decimal("100")),
        energy_kcal=Decimal("2000"),
        eat=Decimal("300"),
        plan=SimpleNamespace(
            measurement=SimpleNamespace(bmr=Decimal("2000")),
            EXERCISE_RATE=Decimal("1.375"),
        ),
    )

    assert _day_tdee(day) == Decimal("2600")


def test_day_type_tdee_returns_zero_without_model():
    """A wrapper without a model yields a zero TDEE instead of querying."""
    assert DayType.tdee(SimpleNamespace(model=None)) == 0.0


def test_week_plan_type_days_fallback_queries_without_model(mocker):
    """Days resolve per-object when the wrapper has no prefetched model."""
    day = mocker.Mock()
    queryset = mocker.Mock()
    queryset.order_by.return_value = [day]
    filter_mock = mocker.patch.object(
        Day.objects, "filter", return_value=queryset
    )
    converted = mocker.Mock()
    mocker.patch(
        "apps.plans.schema.DayType.from_model", return_value=converted
    )
    value = SimpleNamespace(id=9, model=None)

    assert WeekPlanType.days(value) == [converted]
    filter_mock.assert_called_once_with(plan_id=9)


def test_week_plan_type_scalars_return_zero_without_model():
    """TWEE and energy scalars fail soft on model-less wrappers."""
    value = SimpleNamespace(model=None)

    assert WeekPlanType.twee(value) == 0.0
    assert WeekPlanType.energy_kcal_goal(value) == 0.0
    assert WeekPlanType.energy_kcal(value) == 0.0


def test_week_plan_type_energy_scalars_read_model_values():
    """Energy scalars surface the model values when the model is present."""
    value = SimpleNamespace(
        model=SimpleNamespace(
            energy_kcal_goal=Decimal("2000"),
            energy_kcal=Decimal("1500"),
        )
    )

    assert WeekPlanType.energy_kcal_goal(value) == 2000.0
    assert WeekPlanType.energy_kcal(value) == 1500.0


def test_week_plan_validation_rejects_mismatched_daily_inputs(mocker):
    """Validation requires one deficit value for every supplied TDEE."""
    measurement = SimpleNamespace(weight=Decimal("80"), bmr=Decimal("2000"))
    mocker.patch(
        "apps.plans.schema.validated_positive_decimal",
        return_value=Decimal("2"),
    )
    mocker.patch(
        "apps.plans.schema.validated_percentage_decimal",
        return_value=Decimal("20"),
    )
    mocker.patch(
        "apps.plans.schema.validated_non_negative_decimal",
        return_value=Decimal("100"),
    )

    with pytest.raises(ValueError, match="Every day"):
        _validated_week_plan_parameters(
            measurement,
            2,
            20,
            100,
            tdee_values=[Decimal("2000")],
            daily_deficits=[Decimal("10"), Decimal("20")],
        )


@pytest.mark.django_db
@pytest.mark.parametrize("user", [None, AnonymousUser()])
@pytest.mark.parametrize(
    ("resolver", "kwargs"),
    [
        (
            "create_week_plan",
            {
                "start_date": "2026-01-01",
                "protein_g_kg": 2.0,
                "fat_perc": 20.0,
                "deficit": 100,
                "measurement_id": 1,
            },
        ),
        (
            "update_week_plan",
            {"id": "1", "protein_g_kg": 2.0, "fat_perc": 20.0, "deficit": 100},
        ),
        ("delete_week_plan", {"id": "1"}),
        ("update_day", {"id": "1", "tracked": True}),
        (
            "create_intake",
            {"day_id": 1, "meal": "lunch", "num_servings": 1.0},
        ),
        (
            "update_intake",
            {"id": "1", "meal": "lunch", "num_servings": 1.0},
        ),
        ("delete_intake", {"id": "1"}),
    ],
)
def test_plan_mutations_reject_unauthenticated_callers(user, resolver, kwargs):
    """Every plan mutation rejects both missing and anonymous principals."""
    with pytest.raises(PermissionError, match="Authentication required"):
        getattr(PlanMutation(), resolver)(_info(user), **kwargs)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("resolver", "model", "kwargs", "message"),
    [
        (
            "create_week_plan",
            Measurement,
            {
                "start_date": "2026-01-01",
                "protein_g_kg": 2.0,
                "fat_perc": 20.0,
                "deficit": 100,
                "measurement_id": 404,
            },
            "Measurement not found",
        ),
        (
            "update_week_plan",
            WeekPlan,
            {
                "id": "404",
                "protein_g_kg": 2.0,
                "fat_perc": 20.0,
                "deficit": 100,
            },
            "WeekPlan not found",
        ),
        ("delete_week_plan", WeekPlan, {"id": "404"}, "WeekPlan not found"),
        ("update_day", Day, {"id": "404", "tracked": True}, "Day not found"),
        (
            "create_intake",
            Day,
            {"day_id": 404, "meal": "lunch", "num_servings": 1.0},
            "Day not found",
        ),
        (
            "update_intake",
            Intake,
            {"id": "404", "meal": "lunch", "num_servings": 1.0},
            "Intake not found",
        ),
        ("delete_intake", Intake, {"id": "404"}, "Intake not found"),
    ],
)
def test_plan_mutations_translate_missing_owned_objects(
    mocker, resolver, model, kwargs, message
):
    """Mutation ownership lookups expose stable domain errors."""
    mocker.patch.object(model.objects, "get", side_effect=model.DoesNotExist)

    with pytest.raises(ValueError, match=message):
        getattr(PlanMutation(), resolver)(
            _info(_authenticated_user()), **kwargs
        )
