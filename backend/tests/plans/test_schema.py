"""Tests for Plans, Days, and Intakes GraphQL schema."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

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
