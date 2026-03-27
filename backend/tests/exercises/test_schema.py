"""Tests for Exercises GraphQL schema."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.exercises.models import DaySteps, Exercise
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from config.schema import schema

User = get_user_model()


def _create_user_with_day(email: str) -> tuple:
    """Create a user with a week plan and a day.

    Args:
        email (str): user email.

    Returns:
        tuple: (user, day) tuple.
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

    day = Day.objects.filter(plan=plan).first()
    return user, day


@pytest.mark.django_db
class TestExerciseQuery:
    """Tests for exercise queries."""

    def test_exercises_unauthenticated(self):
        """Test exercises query without authentication."""
        # When querying exercises without auth
        query = "{ exercises { id } }"
        result = schema.execute_sync(query, context_value=None)

        # Then the result is an empty list
        assert result.data["exercises"] == []

    def test_exercises_returns_user_data_only(self, mocker):
        """Test exercises returns only the current user's data."""
        # Given two users with exercises
        user1, day1 = _create_user_with_day("ex1@example.com")
        user2, day2 = _create_user_with_day("ex2@example.com")
        Exercise.objects.create(day=day1, time="10:00", type="walk", kcals=200)
        Exercise.objects.create(day=day2, time="11:00", type="run", kcals=400)

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When querying exercises
        query = "{ exercises { id kcals } }"
        result = schema.execute_sync(query, context_value=mock_context)

        # Then only user1's exercise is returned
        assert len(result.data["exercises"]) == 1
        assert result.data["exercises"][0]["kcals"] == 200

    def test_create_exercise(self, mocker):
        """Test creating an exercise."""
        # Given an authenticated user with a day
        user, day = _create_user_with_day("excreate@example.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When creating an exercise
        mutation = """
            mutation CreateExercise(
                $dayId: Int!, $type: String!, $kcals: Int!
            ) {
                createExercise(
                    dayId: $dayId, type: $type, kcals: $kcals
                ) { id type kcals }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "dayId": day.id,
                "type": "gym",
                "kcals": 300,
            },
            context_value=mock_context,
        )

        # Then the exercise is created
        assert result.errors is None
        assert result.data["createExercise"]["type"] == "gym"
        assert result.data["createExercise"]["kcals"] == 300

    def test_delete_exercise(self, mocker):
        """Test deleting an exercise."""
        # Given a user with an exercise
        user, day = _create_user_with_day("exdelete@example.com")
        exercise = Exercise.objects.create(
            day=day, time="10:00", type="walk", kcals=100
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When deleting the exercise
        mutation = """
            mutation DeleteExercise($id: ID!) {
                deleteExercise(id: $id)
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(exercise.id)},
            context_value=mock_context,
        )

        # Then the exercise is deleted
        assert result.errors is None
        assert result.data["deleteExercise"] is True
        assert not Exercise.objects.filter(pk=exercise.id).exists()


@pytest.mark.django_db
class TestDayStepsQuery:
    """Tests for day steps queries."""

    def test_create_day_steps(self, mocker):
        """Test creating day steps."""
        # Given an authenticated user with a day
        user, day = _create_user_with_day("stepcreate@example.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When creating day steps
        mutation = """
            mutation CreateDaySteps(
                $dayId: Int!, $steps: Int!
            ) {
                createDaySteps(
                    dayId: $dayId, steps: $steps
                ) { id steps kcals }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "dayId": day.id,
                "steps": 10000,
            },
            context_value=mock_context,
        )

        # Then the day steps are created with computed kcals
        assert result.errors is None
        data = result.data["createDaySteps"]
        assert data["steps"] == 10000
        assert data["kcals"] is not None

    def test_delete_day_steps(self, mocker):
        """Test deleting day steps."""
        # Given a user with day steps
        user, day = _create_user_with_day("stepdelete@example.com")
        ds = DaySteps.objects.create(day=day, steps=5000)
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When deleting the day steps
        mutation = """
            mutation DeleteDaySteps($id: ID!) {
                deleteDaySteps(id: $id)
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(ds.id)},
            context_value=mock_context,
        )

        # Then it is deleted
        assert result.errors is None
        assert not DaySteps.objects.filter(pk=ds.id).exists()
