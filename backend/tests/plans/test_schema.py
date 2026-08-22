"""Tests for Plans, Days, and Intakes GraphQL schema."""

# This module keeps the complete plan GraphQL contract in one regression suite.
# pylint: disable=too-many-lines,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals

import datetime
from decimal import Decimal
from typing import cast

import pytest
from django.db import connection
from django.db.models.query import QuerySet
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.exercises.models import DaySteps, Exercise
from apps.foods.models import CupboardItem, FoodProduct
from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
)
from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan
from apps.users.models import User
from config.schema import schema


def _create_user_and_plan(email: str) -> tuple:
    """Create a user and a week plan.

    Args:
        email (str): user email.

    Returns:
        tuple: (user, plan) tuple.
    """
    user = cast(
        User,
        User.objects.create_user(
            email=email,
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        ),
    )
    measurement = Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20.0"), weight=Decimal("80.0")
    )
    plan = WeekPlan.objects.create(
        user=user,
        measurement=measurement,
        start_date=datetime.date.today(),
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=Decimal("500.0"),
    )
    return user, plan


def _count_week_plan_nested_queries(
    mocker,
    *,
    user_email: str,
    plan_count: int,
    query: str,
    include_intakes: bool = False,
) -> int:
    """Create many plans and return SQL query count for one GraphQL query."""
    user = cast(
        User,
        User.objects.create_user(
            email=user_email,
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        ),
    )
    measurement = Measurement.objects.create(
        user=user,
        body_fat_perc=Decimal("20.0"),
        weight=Decimal("80.0"),
    )
    for day_offset in range(plan_count):
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=datetime.date.today()
            - datetime.timedelta(days=day_offset),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25.0"),
            deficit=Decimal("500.0"),
        )
        if include_intakes:
            for day in Day.objects.filter(plan=plan):
                Intake.objects.create(day=day, meal=Intake.MEAL_LUNCH)

    mock_context = mocker.Mock()
    mock_context.request.user = user

    with CaptureQueriesContext(connection) as captured:
        result = schema.execute_sync(
            query,
            context_value=mock_context,
        )
    if result.errors is not None:
        raise AssertionError(result.errors[0])
    return len(captured)


@pytest.mark.django_db
class TestWeekPlanSchema:
    """Tests for WeekPlan queries and mutations."""

    def test_week_plans_query(self, mocker):
        """Test week plans query."""
        user, _ = _create_user_and_plan("wp1@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        query = "{ weekPlans { id proteinGKg } }"
        result = schema.execute_sync(query, context_value=mock_context)

        assert len(result.data["weekPlans"]) == 1
        assert result.data["weekPlans"][0]["proteinGKg"] == 1.8


@pytest.mark.django_db
class TestPlanGraphQLBudget:
    """Regression coverage for nested plan queries."""

    def test_week_plans_and_days_query_has_bounded_budget(self, mocker):
        """Day nesting no longer adds query growth per plan."""
        base_query = "{ weekPlans { id days { id dayNum } } }"
        small_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-days-budget-small@test.com",
            plan_count=1,
            query=base_query,
            include_intakes=False,
        )
        large_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-days-budget-large@test.com",
            plan_count=4,
            query=base_query,
            include_intakes=False,
        )

        assert small_count == large_count

    def test_week_plans_tdee_query_has_bounded_budget(self, mocker):
        """TDEE resolution adds no query growth per plan or day."""
        tdee_query = "{ weekPlans { id days { id tdee } } }"
        small_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-tdee-budget-small@test.com",
            plan_count=1,
            query=tdee_query,
            include_intakes=True,
        )
        large_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-tdee-budget-large@test.com",
            plan_count=4,
            query=tdee_query,
            include_intakes=True,
        )

        assert small_count == large_count

    def test_week_plans_twee_query_has_bounded_budget(self, mocker):
        """TWEE aggregation is batched instead of summing per-day TDEE."""
        twee_query = "{ weekPlans { id twee } }"
        small_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-twee-budget-small@test.com",
            plan_count=1,
            query=twee_query,
            include_intakes=True,
        )
        large_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-twee-budget-large@test.com",
            plan_count=4,
            query=twee_query,
            include_intakes=True,
        )

        assert small_count == large_count

    def test_week_plans_scalar_only_query_is_lean(self, mocker):
        """Scalar-only week plan queries skip the days hydration."""
        scalar_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-scalar-budget@test.com",
            plan_count=4,
            query="{ weekPlans { id startDate proteinGKg } }",
            include_intakes=True,
        )

        assert scalar_count == 1

    def test_week_plan_tdee_and_twee_match_model_values(self, mocker):
        """Batched tdee/twee resolution matches the model properties."""
        user, plan = _create_user_and_plan("plan-tdee-values@test.com")
        day = Day.objects.filter(plan=plan).first()
        DaySteps.objects.create(day=day, steps=1000)
        Exercise.objects.create(
            day=day, type=Exercise.EXERCISE_WALK, kcals=100
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            "{ weekPlans { id twee days { id tdee } } }",
            context_value=mock_context,
        )

        assert result.errors is None
        week = result.data["weekPlans"][0]
        assert week["twee"] == float(plan.twee)
        day_tdee = next(
            item["tdee"] for item in week["days"] if item["id"] == str(day.id)
        )
        assert day_tdee == float(day.tdee)

    def test_week_plan_singular_with_days_prefetches(self, mocker):
        """The single-plan path hydrates days with TDEE dependencies."""
        user, plan = _create_user_and_plan("plan-singular-prefetch@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            '{ weekPlan(id: "%s") { id days { id tdee } } }' % plan.id,
            context_value=mock_context,
        )

        assert result.errors is None
        week = result.data["weekPlan"]
        assert week["id"] == str(plan.id)
        assert len(week["days"]) == 7

    def test_day_singular_with_tdee_and_intakes_hydrates(self, mocker):
        """The single-day path hydrates only when nested fields are asked."""
        user, plan = _create_user_and_plan("plan-singular-day@test.com")
        day = Day.objects.filter(plan=plan).first()
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            '{ day(id: "%s") { id tdee intakes { id meal } } }' % day.id,
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["day"]["id"] == str(day.id)
        assert result.data["day"]["intakes"] == []

    def test_week_plans_fragment_query_has_bounded_budget(self, mocker):
        """Named fragment day selections keep the hydration bounded."""
        fragment_query = (
            "{ weekPlans { id ...WeekPlanFragment } } "
            "fragment WeekPlanFragment on WeekPlanType { days { id tdee } }"
        )
        small_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-fragment-budget-small@test.com",
            plan_count=1,
            query=fragment_query,
            include_intakes=True,
        )
        large_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-fragment-budget-large@test.com",
            plan_count=4,
            query=fragment_query,
            include_intakes=True,
        )

        assert small_count == large_count

    def test_week_plans_inline_fragment_query_has_bounded_budget(self, mocker):
        """Inline fragment day selections also trigger the hydration."""
        inline_query = (
            "{ weekPlans { id ... on WeekPlanType { days { id tdee } } } }"
        )
        small_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-inline-fragment-budget-small@test.com",
            plan_count=1,
            query=inline_query,
            include_intakes=True,
        )
        large_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-inline-fragment-budget-large@test.com",
            plan_count=4,
            query=inline_query,
            include_intakes=True,
        )

        assert small_count == large_count

    def test_days_and_intakes_query_has_bounded_budget(self, mocker):
        """Intake nesting no longer adds query growth per day."""
        nested_query = "{ weekPlans { id days { id intakes { id meal } } } }"
        small_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-day-intake-budget-small@test.com",
            plan_count=1,
            query=nested_query,
            include_intakes=True,
        )
        large_count = _count_week_plan_nested_queries(
            mocker,
            user_email="plan-day-intake-budget-large@test.com",
            plan_count=4,
            query=nested_query,
            include_intakes=True,
        )

        assert small_count == large_count

    def test_create_week_plan(self, mocker):
        """Test creating a week plan."""
        user = User.objects.create_user(
            email="wpcreate@test.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=Decimal("20.0"), weight=Decimal("80.0")
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation CreatePlan(
                $startDate: String!, $proteinGKg: Float!,
                $fatPerc: Float!, $deficit: Int!, $measurementId: Int!
            ) {
                createWeekPlan(
                    startDate: $startDate, proteinGKg: $proteinGKg,
                    fatPerc: $fatPerc, deficit: $deficit,
                    measurementId: $measurementId
                ) { id proteinGKg days { id dayNum } }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "startDate": str(datetime.date.today()),
                "proteinGKg": 2.0,
                "fatPerc": 20.0,
                "deficit": 300,
                "measurementId": measurement.id,
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["createWeekPlan"]["proteinGKg"] == 2.0
        # Check that 7 days were generated
        assert len(result.data["createWeekPlan"]["days"]) == 7

    def test_create_week_plan_missing_user_lock_raises_redacted(
        self, mocker, monkeypatch
    ):
        """A vanished user row surfaces the redacted auth error."""
        user = User.objects.create_user(
            email="wplock-redacted@test.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        Measurement.objects.create(
            user=user, body_fat_perc=Decimal("20.0"), weight=Decimal("80.0")
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        def _raise(*args, **kwargs):
            raise User.DoesNotExist("User matching query does not exist.")

        monkeypatch.setattr(
            "apps.plans.schema.lock_user_for_garmin_sync", _raise
        )

        mutation = """
            mutation CreatePlan(
                $startDate: String!, $proteinGKg: Float!,
                $fatPerc: Float!, $deficit: Int!, $measurementId: Int!
            ) {
                createWeekPlan(
                    startDate: $startDate, proteinGKg: $proteinGKg,
                    fatPerc: $fatPerc, deficit: $deficit,
                    measurementId: $measurementId
                ) { id }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "startDate": str(datetime.date.today()),
                "proteinGKg": 2.0,
                "fatPerc": 20.0,
                "deficit": 300,
                "measurementId": Measurement.objects.get(user=user).id,
            },
            context_value=mock_context,
        )

        assert result.errors
        message = str(result.errors[0])
        assert "Authentication required" in message
        assert "matching query does not exist" not in message

    @pytest.mark.parametrize(
        ("operation", "protein_g_kg", "fat_perc", "deficit"),
        [
            ("create", 0.1, 0.1, 0),
            ("update", 2.1, 25.1, 101),
        ],
    )
    def test_week_plan_mutations_accept_representable_values(
        self, mocker, operation, protein_g_kg, fat_perc, deficit
    ):
        """Plan writes preserve one-decimal fields and the integer deficit."""
        user, plan = _create_user_and_plan(
            f"plan-boundary-{operation}@test.com"
        )
        measurement = plan.measurement
        context = mocker.Mock()
        context.request.user = user
        if operation == "create":
            plan.delete()
            mutation = """
                mutation Boundary(
                    $measurementId: Int!, $proteinGKg: Float!,
                    $fatPerc: Float!, $deficit: Int!
                ) {
                    createWeekPlan(
                        startDate: "2026-01-05", measurementId: $measurementId,
                        proteinGKg: $proteinGKg, fatPerc: $fatPerc,
                        deficit: $deficit
                    ) { id }
                }
            """
            variables = {
                "measurementId": measurement.id,
                "proteinGKg": protein_g_kg,
                "fatPerc": fat_perc,
                "deficit": deficit,
            }
        else:
            mutation = """
                mutation Boundary(
                    $id: ID!, $proteinGKg: Float!,
                    $fatPerc: Float!, $deficit: Int!
                ) {
                    updateWeekPlan(
                        id: $id, proteinGKg: $proteinGKg,
                        fatPerc: $fatPerc, deficit: $deficit
                    ) { id }
                }
            """
            variables = {
                "id": str(plan.id),
                "proteinGKg": protein_g_kg,
                "fatPerc": fat_perc,
                "deficit": deficit,
            }

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        persisted = WeekPlan.objects.get(
            pk=result.data[
                "createWeekPlan" if operation == "create" else "updateWeekPlan"
            ]["id"]
        )
        assert persisted.protein_g_kg == Decimal(str(protein_g_kg))
        assert persisted.fat_perc == Decimal(str(fat_perc))
        assert persisted.deficit == deficit

    def test_update_week_plan(self, mocker):
        """Test updating a week plan."""
        user, plan = _create_user_and_plan("wpupd@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation UpdatePlan(
                $id: ID!, $proteinGKg: Float!,
                $fatPerc: Float!, $deficit: Int!
            ) {
                updateWeekPlan(
                    id: $id, proteinGKg: $proteinGKg,
                    fatPerc: $fatPerc, deficit: $deficit
                ) {
                    proteinGKg
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(plan.id),
                "proteinGKg": 2.2,
                "fatPerc": 30.0,
                "deficit": 100,
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateWeekPlan"]["proteinGKg"] == 2.2

        days = list(Day.objects.filter(plan=plan).order_by("day_num"))
        assert [day.deficit for day in days] == [
            90,
            80,
            90,
            110,
            110,
            110,
            110,
        ]
        # Verify that the persisted fields match the model's goal calculators.
        # pylint: disable=protected-access
        for day in days:
            assert day.protein_g_goal == Decimal("176.00")
            assert day.energy_kcal_goal == day._energy_kcal_goal.quantize(
                Decimal("0.01")
            )
            assert day.fat_g_goal == day._fat_g_goal.quantize(Decimal("0.01"))
            assert day.carbs_g_goal == day._carbs_g_goal.quantize(
                Decimal("0.01")
            )
        # pylint: enable=protected-access

    def test_update_week_plan_locks_plan_and_all_days_once(self, mocker):
        """A plan aggregate update acquires canonical lock levels once."""
        user, plan = _create_user_and_plan("wp-lock-order@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user
        locked_models = []
        seen_querysets = []
        original_fetch_all = (
            QuerySet._fetch_all  # pylint: disable=protected-access
        )

        def record_locked_queryset(queryset):
            if queryset.query.select_for_update and not any(
                queryset is seen for seen in seen_querysets
            ):
                seen_querysets.append(queryset)
                locked_models.append(queryset.model)
            return original_fetch_all(queryset)

        mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

        result = schema.execute_sync(
            """
                mutation UpdatePlan($id: ID!) {
                    updateWeekPlan(
                        id: $id, proteinGKg: 2.0, fatPerc: 25, deficit: 100
                    ) { id }
                }
            """,
            variable_values={"id": str(plan.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert locked_models == [WeekPlan, Day]

    @pytest.mark.parametrize("operation", ["create", "update"])
    @pytest.mark.parametrize(
        ("field_name", "value", "error"),
        [
            ("proteinGKg", -0.1, "proteinGKg must be greater than 0"),
            ("proteinGKg", 0.0, "proteinGKg must be greater than 0"),
            ("proteinGKg", 0.01, None),
            ("proteinGKg", 1000000000.0, None),
            ("proteinGKg", float("nan"), None),
            ("proteinGKg", float("inf"), None),
            (
                "fatPerc",
                0.0,
                "fatPerc must be greater than 0 and less than 100",
            ),
            (
                "fatPerc",
                100.0,
                "fatPerc must be greater than 0 and less than 100",
            ),
            ("fatPerc", 99.99, None),
            ("fatPerc", float("nan"), None),
            ("fatPerc", float("inf"), None),
            ("deficit", -1, "deficit must be greater than or equal to 0"),
            ("deficit", 2000, "energyKcalGoal must be greater than 0"),
            (
                "proteinGKg",
                10.0,
                "carbsGGoal must be greater than or equal to 0",
            ),
            ("fatPerc", 99.0, "carbsGGoal must be greater than or equal to 0"),
        ],
    )
    # pylint: disable-next=R0913,R0917,R0914
    def test_week_plan_rejects_invalid_inputs_without_partial_writes(
        self, mocker, operation, field_name, value, error
    ):
        """Invalid plan inputs cannot persist a plan or regenerate its days."""
        user, plan = _create_user_and_plan(
            f"plan-invalid-{operation}-{field_name}-{repr(value)}@test.com"
        )
        measurement = plan.measurement
        context = mocker.Mock()
        context.request.user = user
        values = {"proteinGKg": 2.0, "fatPerc": 25.0, "deficit": 100}
        values[field_name] = value

        if operation == "create":
            plan.delete()
            mutation = """
                mutation InvalidPlan(
                    $proteinGKg: Float!, $fatPerc: Float!, $deficit: Int!,
                    $measurementId: Int!
                ) {
                    createWeekPlan(
                        startDate: "2026-01-05", proteinGKg: $proteinGKg,
                        fatPerc: $fatPerc, deficit: $deficit,
                        measurementId: $measurementId
                    ) { id }
                }
            """
            variables = {**values, "measurementId": measurement.id}
            original_plan_count = WeekPlan.objects.count()
            original_day_count = Day.objects.count()
        else:
            mutation = """
                mutation InvalidPlan(
                    $id: ID!, $proteinGKg: Float!, $fatPerc: Float!,
                    $deficit: Int!
                ) {
                    updateWeekPlan(
                        id: $id, proteinGKg: $proteinGKg,
                        fatPerc: $fatPerc, deficit: $deficit
                    ) { id }
                }
            """
            variables = {**values, "id": str(plan.id)}
            original_plan_state = (
                plan.protein_g_kg,
                plan.fat_perc,
                plan.deficit,
            )
            original_days = list(
                plan.days.order_by("day_num").values_list(
                    "id",
                    "deficit",
                    "energy_kcal_goal",
                    "protein_g_goal",
                    "fat_g_goal",
                    "carbs_g_goal",
                )
            )

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        if error is not None:
            assert error in str(result.errors[0])
        if operation == "create":
            assert WeekPlan.objects.count() == original_plan_count
            assert Day.objects.count() == original_day_count
        else:
            plan.refresh_from_db()
            assert (plan.protein_g_kg, plan.fat_perc, plan.deficit) == (
                original_plan_state
            )
            assert (
                list(
                    plan.days.order_by("day_num").values_list(
                        "id",
                        "deficit",
                        "energy_kcal_goal",
                        "protein_g_goal",
                        "fat_g_goal",
                        "carbs_g_goal",
                    )
                )
                == original_days
            )

    def test_delete_week_plan(self, mocker):
        """Test deleting a week plan."""
        user, plan = _create_user_and_plan("wpdel@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = "mutation DeletePlan($id: ID!) { deleteWeekPlan(id: $id) }"
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(plan.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["deleteWeekPlan"] is True
        assert not WeekPlan.objects.filter(pk=plan.id).exists()


@pytest.mark.django_db
class TestDaySchema:
    """Tests for Day queries and mutations."""

    def test_day_query(self, mocker):
        """Test day query."""
        user, plan = _create_user_and_plan("dayquery@test.com")
        day = Day.objects.filter(plan=plan).first()
        mock_context = mocker.Mock()
        mock_context.request.user = user

        query = "query GetDay($id: ID!) { day(id: $id) { dayNum tracked } }"
        result = schema.execute_sync(
            query,
            variable_values={"id": str(day.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["day"]["dayNum"] == day.day_num
        assert result.data["day"]["tracked"] is True

    def test_update_day(self, mocker):
        """Test updating a day."""
        user, plan = _create_user_and_plan("dayupd@test.com")
        day = Day.objects.filter(plan=plan).first()
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation UpdateDay($id: ID!, $tracked: Boolean!) {
                updateDay(id: $id, tracked: $tracked) { tracked }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(day.id), "tracked": True},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateDay"]["tracked"] is True


@pytest.mark.django_db
class TestIntakeSchema:
    """Tests for Intake mutations."""

    @pytest.mark.parametrize("meal", ["", "   ", "brunch", "Lunch", "dinner!"])
    def test_create_intake_rejects_invalid_meal(self, mocker, meal):
        """Only supported meal names are accepted for createIntake."""
        user, plan = _create_user_and_plan(
            f"intake-invalid-meal-create-{meal.replace(' ', '-') or 'space'}@test.com"
        )
        day = Day.objects.filter(plan=plan).first()
        mock_context = mocker.Mock()
        mock_context.request.user = user
        result = schema.execute_sync(
            """
                mutation CreateIntake(
                    $dayId: Int!, $meal: String!, $numServings: Float!
                ) {
                    createIntake(
                        dayId: $dayId, meal: $meal, numServings: $numServings,
                        energyKcal: 100
                    ) { id }
                }
            """,
            variable_values={
                "dayId": day.id,
                "meal": meal,
                "numServings": 1,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "meal must be one of: breakfast, lunch, snack, dinner" in str(
            result.errors[0]
        )
        assert not Intake.objects.filter(day=day).exists()

    @pytest.mark.parametrize("meal", ["", "   ", "brunch", "Lunch", "snacK"])
    def test_update_intake_rejects_invalid_meal(self, mocker, meal):
        """Only supported meal names are accepted for updateIntake."""
        user, plan = _create_user_and_plan(
            f"intake-invalid-meal-update-{meal.replace(' ', '-') or 'space'}@test.com"
        )
        day = Day.objects.filter(plan=plan).first()
        intake = Intake.objects.create(
            day=day,
            meal="lunch",
            num_servings=1,
            energy_kcal=200,
            protein_g=15,
        )
        original_intake_state = (
            intake.meal,
            intake.num_servings,
            intake.energy_kcal,
            intake.protein_g,
            intake.fat_g,
            intake.carbs_g,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation UpdateIntake(
                    $id: ID!, $meal: String!, $numServings: Float!
                ) {
                    updateIntake(
                        id: $id, meal: $meal, numServings: $numServings,
                        energyKcal: 300
                    ) { id }
                }
            """,
            variable_values={
                "id": str(intake.id),
                "meal": meal,
                "numServings": 2,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "meal must be one of: breakfast, lunch, snack, dinner" in str(
            result.errors[0]
        )
        intake.refresh_from_db()
        assert (
            intake.meal,
            intake.num_servings,
            intake.energy_kcal,
            intake.protein_g,
            intake.fat_g,
            intake.carbs_g,
        ) == original_intake_state

    def test_create_intake_custom(self, mocker):
        """Test creating a custom intake with direct macros."""
        user, plan = _create_user_and_plan("intcreate@test.com")
        day = Day.objects.filter(plan=plan).first()
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation CreateIntake(
                $dayId: Int!, $meal: String!, $numServings: Float!,
                $energyKcal: Float, $proteinG: Float
            ) {
                createIntake(
                    dayId: $dayId, meal: $meal, numServings: $numServings,
                    energyKcal: $energyKcal, proteinG: $proteinG
                ) { energyKcal meal }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "dayId": day.id,
                "meal": "lunch",
                "numServings": 1.5,
                "energyKcal": 400.0,
                "proteinG": 30.0,
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["createIntake"]["meal"] == "lunch"
        assert result.data["createIntake"]["energyKcal"] == 400.0

        intake = Intake.objects.get(day=day)
        assert intake.processed is True

        day.refresh_from_db()
        assert day.energy_kcal == Decimal("400.00")
        assert day.protein_g == Decimal("30.00")
        assert plan.energy_kcal == Decimal("400.00")

    @pytest.mark.parametrize(
        "field", ["energyKcal", "proteinG", "fatG", "carbsG"]
    )
    @pytest.mark.parametrize(
        "value",
        [-1.0, 0.001, 100000000.0, float("nan"), float("inf"), -float("inf")],
    )
    def test_create_custom_intake_rejects_invalid_macros_without_writes(
        self, mocker, field, value
    ):
        """Invalid custom macros do not create an intake or alter rollups."""
        user, plan = _create_user_and_plan(
            f"custom-create-{field}-{repr(value)}@example.com"
        )
        day = Day.objects.filter(plan=plan).first()
        original_day_state = (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
        )
        original_plan_energy = plan.energy_kcal
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateCustomIntake(
                $dayId: Int!, $energyKcal: Float,
                $proteinG: Float, $fatG: Float, $carbsG: Float
            ) {
                createIntake(
                    dayId: $dayId, meal: "lunch", numServings: 1,
                    energyKcal: $energyKcal, proteinG: $proteinG,
                    fatG: $fatG, carbsG: $carbsG
                ) { id }
            }
        """
        variables = {
            "dayId": day.id,
            "energyKcal": 0.0,
            "proteinG": 0.0,
            "fatG": 0.0,
            "carbsG": 0.0,
        }
        variables[field] = value

        result = schema.execute_sync(
            mutation,
            variable_values=variables,
            context_value=mock_context,
        )

        assert result.errors is not None
        assert not Intake.objects.filter(day=day).exists()
        day.refresh_from_db()
        plan.refresh_from_db()
        assert (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
        ) == original_day_state
        assert plan.energy_kcal == original_plan_energy

    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_food_backed_intakes_ignore_direct_macro_inputs(
        self, mocker, operation
    ):
        """Food-backed create and update always persist derived nutrients."""
        user, plan = _create_user_and_plan(
            f"food-macros-{operation}@example.com"
        )
        day = Day.objects.filter(plan=plan).first()
        product = FoodProduct.objects.create(
            name=f"Derived macro food {operation}",
            nutritional_info_size=100,
            nutritional_info_unit="g",
            size=200,
            size_unit="g",
            num_servings=2,
            energy_kcal=100,
            protein_g=10,
            fat_g=5,
            carbs_g=20,
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        intake = None
        if operation == "update":
            intake = Intake.objects.create(
                day=day,
                food=serving,
                meal="lunch",
                num_servings=1,
            )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        direct_macros = """
            energyKcal: -1, proteinG: -1, fatG: -1, carbsG: -1
        """
        if operation == "create":
            mutation = f"""
                mutation CreateFoodIntake($dayId: Int!, $foodId: ID!) {{
                    createIntake(
                        dayId: $dayId, foodId: $foodId,
                        meal: "lunch", numServings: 2,
                        {direct_macros}
                    ) {{ id }}
                }}
            """
            variables = {"dayId": day.id, "foodId": str(serving.id)}
        else:
            assert intake is not None
            mutation = f"""
                mutation UpdateFoodIntake($id: ID!) {{
                    updateIntake(
                        id: $id, meal: "dinner", numServings: 2,
                        {direct_macros}
                    ) {{ id }}
                }}
            """
            variables = {"id": str(intake.id)}

        result = schema.execute_sync(
            mutation,
            variable_values=variables,
            context_value=mock_context,
        )

        assert result.errors is None
        persisted = Intake.objects.get(
            pk=result.data[
                "createIntake" if operation == "create" else "updateIntake"
            ]["id"]
        )
        assert (
            persisted.energy_kcal,
            persisted.protein_g,
            persisted.fat_g,
            persisted.carbs_g,
        ) == (
            Decimal("200.00"),
            Decimal("20.00"),
            Decimal("10.00"),
            Decimal("40.00"),
        )

    @pytest.mark.parametrize("food_backed", [False, True])
    @pytest.mark.parametrize(
        ("operation", "num_servings", "nutrient"),
        [("create", 0.1, 12.34), ("update", 99.9, 56.78)],
    )
    def test_intake_mutations_accept_representable_decimal_boundaries(
        self, mocker, operation, num_servings, nutrient, food_backed
    ):
        """Custom and food-backed intakes preserve supported serving precision."""
        user, plan = _create_user_and_plan(
            f"intake-boundary-{operation}-{food_backed}@test.com"
        )
        day = Day.objects.filter(plan=plan).first()
        product = FoodProduct.objects.create(
            name=f"Boundary intake {operation} {food_backed}",
            energy_kcal=10,
            protein_g=2,
            fat_g=1,
            carbs_g=3,
        )
        food = product.servings.get(serving_size=100, serving_unit="g")
        intake = Intake.objects.create(
            day=day,
            food=food if food_backed else None,
            meal="lunch",
            num_servings=1,
            energy_kcal=1,
            protein_g=1,
            fat_g=1,
            carbs_g=1,
        )
        context = mocker.Mock()
        context.request.user = user
        if operation == "create":
            intake.delete()
            mutation = """
                mutation Boundary(
                    $dayId: Int!, $foodId: ID, $numServings: Float!,
                    $nutrient: Float
                ) {
                    createIntake(
                        dayId: $dayId, foodId: $foodId, meal: "lunch",
                        numServings: $numServings, energyKcal: $nutrient,
                        proteinG: $nutrient, fatG: $nutrient,
                        carbsG: $nutrient
                    ) { id }
                }
            """
            variables = {
                "dayId": day.id,
                "foodId": str(food.id) if food_backed else None,
                "numServings": num_servings,
                "nutrient": nutrient,
            }
        else:
            mutation = """
                mutation Boundary(
                    $id: ID!, $numServings: Float!, $nutrient: Float
                ) {
                    updateIntake(
                        id: $id, meal: "dinner", numServings: $numServings,
                        energyKcal: $nutrient, proteinG: $nutrient,
                        fatG: $nutrient, carbsG: $nutrient
                    ) { id }
                }
            """
            variables = {
                "id": str(intake.id),
                "numServings": num_servings,
                "nutrient": nutrient,
            }

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        persisted = Intake.objects.get(
            pk=result.data[
                "createIntake" if operation == "create" else "updateIntake"
            ]["id"]
        )
        assert persisted.num_servings == Decimal(str(num_servings))
        expected_nutrients = (
            (
                Decimal("10") * Decimal(str(num_servings)),
                Decimal("2") * Decimal(str(num_servings)),
                Decimal("1") * Decimal(str(num_servings)),
                Decimal("3") * Decimal(str(num_servings)),
            )
            if food_backed
            else (Decimal(str(nutrient)),) * 4
        )
        assert (
            persisted.energy_kcal,
            persisted.protein_g,
            persisted.fat_g,
            persisted.carbs_g,
        ) == expected_nutrients

    def test_create_food_intake_overconsumption_rolls_back_everything(
        self, mocker
    ):
        """Failed create leaves no intake or aggregate and cupboard changes."""
        user, plan = _create_user_and_plan("intake-create-atomic@test.com")
        day = Day.objects.filter(plan=plan).first()
        product = FoodProduct.objects.create(
            name="Create atomic food",
            nutritional_info_size=100,
            nutritional_info_unit="g",
            size=400,
            size_unit="g",
            num_servings=4,
            energy_kcal=100,
            protein_g=10,
            fat_g=5,
            carbs_g=20,
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        cupboard_item = CupboardItem.objects.create(
            owner=user,
            food=product,
            purchased_at=timezone.now(),
        )
        original_day_state = (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
            day.energy_kcal_intake_perc,
            day.protein_g_intake_perc,
            day.fat_g_intake_perc,
            day.carbs_g_intake_perc,
            day.breakfast_flag,
            day.lunch_flag,
            day.snack_flag,
            day.dinner_flag,
            day.completed,
        )
        original_plan_state = (plan.energy_kcal, plan.completed)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateIntake($dayId: Int!, $foodId: ID!) {
                createIntake(
                    dayId: $dayId, foodId: $foodId,
                    meal: "lunch", numServings: 5
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"dayId": day.id, "foodId": str(serving.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert isinstance(
            result.errors[0].original_error,
            CupboardItemConsumptionTooBigError,
        )
        day.refresh_from_db()
        plan.refresh_from_db()
        cupboard_item.refresh_from_db()
        assert not Intake.objects.filter(day=day).exists()
        assert (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
            day.energy_kcal_intake_perc,
            day.protein_g_intake_perc,
            day.fat_g_intake_perc,
            day.carbs_g_intake_perc,
            day.breakfast_flag,
            day.lunch_flag,
            day.snack_flag,
            day.dinner_flag,
            day.completed,
        ) == original_day_state
        assert (plan.energy_kcal, plan.completed) == original_plan_state
        assert cupboard_item.consumed_perc == 0
        assert not cupboard_item.consumptions.exists()

    @pytest.mark.parametrize(
        "num_servings",
        [
            0.0,
            0.01,
            1000000000.0,
            -1.0,
            float("nan"),
            float("inf"),
            -float("inf"),
        ],
    )
    @pytest.mark.parametrize("food_backed", [False, True])
    @pytest.mark.parametrize("operation", ["create", "update"])
    # pylint: disable-next=too-many-locals
    def test_intake_rejects_invalid_num_servings_without_partial_writes(
        self, mocker, operation, food_backed, num_servings
    ):
        """All intake write paths require a finite positive serving count."""
        user, plan = _create_user_and_plan(
            f"intake-invalid-{operation}-{food_backed}-{repr(num_servings)}@test.com"
        )
        day = Day.objects.filter(plan=plan).first()
        food = None
        if food_backed:
            product = FoodProduct.objects.create(
                name=f"Invalid intake food {operation} {repr(num_servings)}",
                nutritional_info_size=100,
                nutritional_info_unit="g",
                size=100,
                size_unit="g",
                num_servings=1,
                energy_kcal=100,
                protein_g=10,
            )
            food = product.servings.get(serving_size=100, serving_unit="g")

        intake = None
        if operation == "update":
            intake = Intake.objects.create(
                day=day,
                food=food,
                meal="lunch",
                num_servings=1,
                energy_kcal=100 if not food_backed else 0,
                protein_g=10 if not food_backed else 0,
            )

        day.refresh_from_db()
        plan.refresh_from_db()
        original_day_state = (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
            day.energy_kcal_intake_perc,
            day.protein_g_intake_perc,
            day.fat_g_intake_perc,
            day.carbs_g_intake_perc,
            day.breakfast_flag,
            day.lunch_flag,
            day.snack_flag,
            day.dinner_flag,
            day.completed,
        )
        original_plan_state = (plan.energy_kcal, plan.completed)
        original_intake_state = None
        if intake:
            original_intake_state = (
                intake.meal,
                intake.num_servings,
                intake.energy_kcal,
                intake.protein_g,
                intake.fat_g,
                intake.carbs_g,
                intake.processed,
            )

        mock_context = mocker.Mock()
        mock_context.request.user = user
        if operation == "create":
            mutation = """
                mutation CreateIntake(
                    $dayId: Int!, $foodId: ID, $numServings: Float!
                ) {
                    createIntake(
                        dayId: $dayId, foodId: $foodId,
                        meal: "dinner", numServings: $numServings,
                        energyKcal: 999, proteinG: 99
                    ) { id }
                }
            """
            variable_values = {
                "dayId": day.id,
                "foodId": str(food.id) if food else None,
                "numServings": num_servings,
            }
        else:
            assert intake is not None
            mutation = """
                mutation UpdateIntake($id: ID!, $numServings: Float!) {
                    updateIntake(
                        id: $id, meal: "dinner",
                        numServings: $numServings,
                        energyKcal: 999, proteinG: 99
                    ) { id }
                }
            """
            variable_values = {
                "id": str(intake.id),
                "numServings": num_servings,
            }

        result = schema.execute_sync(
            mutation,
            variable_values=variable_values,
            context_value=mock_context,
        )

        assert result.errors is not None
        if num_servings in (0.0, -1.0):
            assert "numServings must be greater than 0" in str(
                result.errors[0]
            )
        day.refresh_from_db()
        plan.refresh_from_db()
        assert (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
            day.energy_kcal_intake_perc,
            day.protein_g_intake_perc,
            day.fat_g_intake_perc,
            day.carbs_g_intake_perc,
            day.breakfast_flag,
            day.lunch_flag,
            day.snack_flag,
            day.dinner_flag,
            day.completed,
        ) == original_day_state
        assert (plan.energy_kcal, plan.completed) == original_plan_state
        if operation == "create":
            assert not Intake.objects.filter(day=day).exists()
        else:
            assert intake is not None
            intake.refresh_from_db()
            assert (
                intake.meal,
                intake.num_servings,
                intake.energy_kcal,
                intake.protein_g,
                intake.fat_g,
                intake.carbs_g,
                intake.processed,
            ) == original_intake_state

    def test_update_intake(self, mocker):
        """Test updating an intake."""
        user, plan = _create_user_and_plan("intupd@test.com")
        day = Day.objects.filter(plan=plan).first()
        intake = Intake.objects.create(
            day=day,
            meal="lunch",
            num_servings=1,
            energy_kcal=200,
            protein_g=15,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation UpdateIntake(
                $id: ID!, $meal: String!,
                $numServings: Float!, $energyKcal: Float!
            ) {
                updateIntake(
                    id: $id, meal: $meal, numServings: $numServings,
                    energyKcal: $energyKcal
                ) {
                    energyKcal numServings
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(intake.id),
                "meal": "lunch",
                "numServings": 2.0,
                "energyKcal": 400.0,
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateIntake"]["energyKcal"] == 400.0
        assert result.data["updateIntake"]["numServings"] == 2.0

    @pytest.mark.parametrize(
        "field", ["energyKcal", "proteinG", "fatG", "carbsG"]
    )
    @pytest.mark.parametrize(
        "value",
        [-1.0, 0.001, 100000000.0, float("nan"), float("inf"), -float("inf")],
    )
    def test_update_custom_intake_rejects_invalid_macros_without_writes(
        self, mocker, field, value
    ):
        """Invalid custom macro updates leave the intake and rollups unchanged."""
        user, plan = _create_user_and_plan(
            f"custom-update-{field}-{repr(value)}@example.com"
        )
        day = Day.objects.filter(plan=plan).first()
        intake = Intake.objects.create(
            day=day,
            meal="lunch",
            num_servings=1,
            energy_kcal=200,
            protein_g=15,
            fat_g=8,
            carbs_g=25,
        )
        day.refresh_from_db()
        plan.refresh_from_db()
        original_intake_state = (
            intake.meal,
            intake.num_servings,
            intake.energy_kcal,
            intake.protein_g,
            intake.fat_g,
            intake.carbs_g,
            intake.processed,
        )
        original_day_state = (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
        )
        original_plan_energy = plan.energy_kcal
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateCustomIntake(
                $id: ID!, $energyKcal: Float,
                $proteinG: Float, $fatG: Float, $carbsG: Float
            ) {
                updateIntake(
                    id: $id, meal: "dinner", numServings: 2,
                    energyKcal: $energyKcal, proteinG: $proteinG,
                    fatG: $fatG, carbsG: $carbsG
                ) { id }
            }
        """
        variables = {
            "id": str(intake.id),
            "energyKcal": 300.0,
            "proteinG": 30.0,
            "fatG": 12.0,
            "carbsG": 40.0,
        }
        variables[field] = value

        result = schema.execute_sync(
            mutation,
            variable_values=variables,
            context_value=mock_context,
        )

        assert result.errors is not None
        intake.refresh_from_db()
        day.refresh_from_db()
        plan.refresh_from_db()
        assert (
            intake.meal,
            intake.num_servings,
            intake.energy_kcal,
            intake.protein_g,
            intake.fat_g,
            intake.carbs_g,
            intake.processed,
        ) == original_intake_state
        assert (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
        ) == original_day_state
        assert plan.energy_kcal == original_plan_energy

    def test_update_food_intake_overconsumption_rolls_back_everything(
        self, mocker
    ):
        """Failed cupboard consumption leaves intake and aggregates unchanged."""
        user, plan = _create_user_and_plan("intake-atomic@test.com")
        day = Day.objects.filter(plan=plan).first()
        product = FoodProduct.objects.create(
            name="Atomic food",
            nutritional_info_size=100,
            nutritional_info_unit="g",
            size=400,
            size_unit="g",
            num_servings=4,
            energy_kcal=100,
            protein_g=10,
            fat_g=5,
            carbs_g=20,
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        cupboard_item = CupboardItem.objects.create(
            owner=user,
            food=product,
            purchased_at=timezone.now(),
        )
        intake = Intake.objects.create(
            day=day,
            meal="lunch",
            num_servings=1,
            food=serving,
        )
        day.refresh_from_db()
        cupboard_item.refresh_from_db()
        original_totals = (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
            plan.energy_kcal,
        )
        original_consumption = cupboard_item.consumed_perc
        original_consumption_id = intake.cupboard_item_consumption.id
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateIntake($id: ID!) {
                updateIntake(
                    id: $id, meal: "dinner", numServings: 5
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(intake.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert isinstance(
            result.errors[0].original_error,
            CupboardItemConsumptionTooBigError,
        )
        intake.refresh_from_db()
        day.refresh_from_db()
        cupboard_item.refresh_from_db()
        assert intake.meal == "lunch"
        assert intake.num_servings == 1
        assert (
            day.energy_kcal,
            day.protein_g,
            day.fat_g,
            day.carbs_g,
            plan.energy_kcal,
        ) == original_totals
        assert cupboard_item.consumed_perc == original_consumption
        assert intake.cupboard_item_consumption.id == original_consumption_id

    def test_delete_intake(self, mocker):
        """Test deleting an intake."""
        user, plan = _create_user_and_plan("intdel@test.com")
        day = Day.objects.filter(plan=plan).first()
        intake = Intake.objects.create(
            day=day,
            meal="lunch",
            num_servings=1,
            energy_kcal=200,
            protein_g=15,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = "mutation DeleteIntake($id: ID!) { deleteIntake(id: $id) }"
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(intake.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["deleteIntake"] is True
        assert not Intake.objects.filter(pk=intake.id).exists()
