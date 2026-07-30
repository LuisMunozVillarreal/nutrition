"""Tests for Plans, Days, and Intakes GraphQL schema."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.foods.models import CupboardItem, FoodProduct
from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
)
from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan
from config.schema import schema

User = get_user_model()


def _create_user_and_plan(email: str) -> tuple:
    """Create a user and a week plan.

    Args:
        email (str): user email.

    Returns:
        tuple: (user, plan) tuple.
    """
    user = User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
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
        "value", [-1.0, float("nan"), float("inf"), -float("inf")]
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
        [0.0, -1.0, float("nan"), float("inf"), -float("inf")],
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
        "value", [-1.0, float("nan"), float("inf"), -float("inf")]
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
