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

CANONICAL_DURATIONS = [
    "00:00:00",
    "00:30:00",
    "24:00:00",
    "25:00:00",
    "72:15:30",
]
DURATION_ERROR = (
    "duration must use HH:MM:SS with total hours and 00-59 minutes/seconds"
)
MALFORMED_DURATIONS = [
    "",
    "1:00:00",
    "000:00:00",
    "00:30",
    "00:00:00:00",
    "00:60:00",
    "00:00:60",
    "-01:00:00",
    "+01:00:00",
    "NaN:00:00",
    "Infinity:00:00",
    "00.5:00:00",
    " 01:00:00",
    "01:00:00\n",
    "1 day, 1:00:00",
    "24000000000:00:00",
]


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
        _, day2 = _create_user_with_day("ex2@example.com")
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

    @pytest.mark.parametrize(
        ("variables", "message"),
        [
            ({"type": "swim"}, "type must be one of: walk, run, cycle, gym"),
            ({"kcals": -1}, "kcals must be greater than or equal to 0"),
            (
                {"distance": -0.01},
                "distance must be greater than or equal to 0",
            ),
            (
                {"distance": 1.001},
                "distance must have at most 2 decimal places",
            ),
            (
                {"distance": 100000000.0},
                "distance must be less than or equal to 99999999.99",
            ),
        ],
    )
    def test_create_exercise_rejects_invalid_values_before_writes(
        self, mocker, variables, message
    ):
        """Invalid exercise values return stable errors without creating rows."""
        user, day = _create_user_with_day(
            f"invalid-exercise-create-{message[:8]}@example.com"
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        supplied = {
            "dayId": day.id,
            "type": "walk",
            "kcals": 100,
            "distance": 1.25,
        }
        supplied.update(variables)

        result = schema.execute_sync(
            """
                mutation CreateExercise(
                    $dayId: Int!, $type: String!, $kcals: Int!,
                    $distance: Float
                ) {
                    createExercise(
                        dayId: $dayId, type: $type, kcals: $kcals,
                        distance: $distance
                    ) { id }
                }
            """,
            variable_values=supplied,
            context_value=mock_context,
        )

        assert result.errors is not None
        assert result.errors[0].message == message
        assert not Exercise.objects.filter(day=day).exists()

    def test_create_exercise_preserves_zero_distance(self, mocker):
        """An explicit zero distance is distinct from an omitted distance."""
        user, day = _create_user_with_day("zero-distance-create@example.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation CreateExercise($dayId: Int!) {
                    createExercise(
                        dayId: $dayId, type: "walk", kcals: 0,
                        distance: 0
                    ) { kcals distance }
                }
            """,
            variable_values={"dayId": day.id},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["createExercise"] == {"kcals": 0, "distance": 0.0}
        exercise = Exercise.objects.get(day=day)
        assert exercise.kcals == 0
        assert exercise.distance == Decimal("0.00")

    @pytest.mark.parametrize("duration", CANONICAL_DURATIONS)
    def test_create_exercise_duration_round_trips_canonical_value(
        self, mocker, duration
    ):
        """Canonical total-hour durations serialize exactly as submitted."""
        user, day = _create_user_with_day(
            f"duration-create-{duration.replace(':', '-')}@example.com"
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation CreateExercise($dayId: Int!, $duration: String!) {
                    createExercise(
                        dayId: $dayId, type: "walk", kcals: 100,
                        duration: $duration
                    ) { duration }
                }
            """,
            variable_values={"dayId": day.id, "duration": duration},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["createExercise"]["duration"] == duration
        exercise = Exercise.objects.get(day=day)
        hours, minutes, seconds = (int(part) for part in duration.split(":"))
        assert exercise.duration == datetime.timedelta(
            hours=hours, minutes=minutes, seconds=seconds
        )

    @pytest.mark.parametrize("duration", MALFORMED_DURATIONS)
    def test_create_exercise_rejects_malformed_duration_before_writes(
        self, mocker, duration
    ):
        """Malformed duration input returns one canonical error without a write."""
        user, day = _create_user_with_day(
            "duration-invalid-create@example.com"
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation CreateExercise($dayId: Int!, $duration: String!) {
                    createExercise(
                        dayId: $dayId, type: "walk", kcals: 100,
                        duration: $duration
                    ) { id }
                }
            """,
            variable_values={"dayId": day.id, "duration": duration},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert result.errors[0].message == DURATION_ERROR
        assert not Exercise.objects.filter(day=day).exists()

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
class TestUpdateExercise:
    """Tests for update exercise validation."""

    @pytest.mark.parametrize(
        ("variables", "message"),
        [
            ({"type": "swim"}, "type must be one of: walk, run, cycle, gym"),
            ({"kcals": -1}, "kcals must be greater than or equal to 0"),
            (
                {"distance": -0.01},
                "distance must be greater than or equal to 0",
            ),
            (
                {"distance": 1.001},
                "distance must have at most 2 decimal places",
            ),
            (
                {"distance": 100000000.0},
                "distance must be less than or equal to 99999999.99",
            ),
        ],
    )
    def test_update_rejects_invalid_values_without_changes(
        self, mocker, variables, message
    ):
        """Update applies the same stable validation as create."""
        user, day = _create_user_with_day(
            f"invalid-exercise-update-{message[:8]}@example.com"
        )
        exercise = Exercise.objects.create(
            day=day,
            time="10:00",
            type="walk",
            kcals=100,
            distance=Decimal("1.25"),
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        supplied = {
            "id": str(exercise.id),
            "type": "run",
            "kcals": 200,
            "distance": 2.5,
        }
        supplied.update(variables)

        result = schema.execute_sync(
            """
                mutation UpdateExercise(
                    $id: ID!, $type: String!, $kcals: Int!,
                    $distance: Float
                ) {
                    updateExercise(
                        id: $id, type: $type, kcals: $kcals,
                        distance: $distance
                    ) { id }
                }
            """,
            variable_values=supplied,
            context_value=mock_context,
        )

        assert result.errors is not None
        assert result.errors[0].message == message
        exercise.refresh_from_db()
        assert exercise.type == "walk"
        assert exercise.kcals == 100
        assert exercise.distance == Decimal("1.25")

    def test_update_preserves_zero_distance(self, mocker):
        """Update stores and serializes an explicit zero distance."""
        user, day = _create_user_with_day("zero-distance-update@example.com")
        exercise = Exercise.objects.create(
            day=day,
            time="10:00",
            type="walk",
            kcals=100,
            distance=Decimal("1.25"),
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation UpdateExercise($id: ID!) {
                    updateExercise(
                        id: $id, type: "run", kcals: 0, distance: 0
                    ) { kcals distance }
                }
            """,
            variable_values={"id": str(exercise.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateExercise"] == {"kcals": 0, "distance": 0.0}
        exercise.refresh_from_db()
        assert exercise.kcals == 0
        assert exercise.distance == Decimal("0.00")

    @pytest.mark.parametrize("duration", CANONICAL_DURATIONS)
    def test_update_exercise_duration_round_trips_canonical_value(
        self, mocker, duration
    ):
        """Update accepts and exactly serializes canonical total-hour values."""
        user, day = _create_user_with_day("duration-update@example.com")
        exercise = Exercise.objects.create(
            day=day,
            time="10:00",
            type="walk",
            kcals=100,
            duration=datetime.timedelta(minutes=15),
            distance=Decimal("1.25"),
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation UpdateExercise($id: ID!, $duration: String!) {
                    updateExercise(
                        id: $id, time: "11:30", type: "run", kcals: 200,
                        duration: $duration, distance: 2.5
                    ) { time type kcals duration distance }
                }
            """,
            variable_values={"id": str(exercise.id), "duration": duration},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateExercise"] == {
            "time": "11:30:00",
            "type": "run",
            "kcals": 200,
            "duration": duration,
            "distance": 2.5,
        }
        exercise.refresh_from_db()
        hours, minutes, seconds = (int(part) for part in duration.split(":"))
        assert exercise.duration == datetime.timedelta(
            hours=hours, minutes=minutes, seconds=seconds
        )

    @pytest.mark.parametrize("duration", MALFORMED_DURATIONS)
    def test_update_exercise_rejects_malformed_duration_without_changes(
        self, mocker, duration
    ):
        """Malformed update duration returns a stable error and preserves the row."""
        user, day = _create_user_with_day(
            "duration-invalid-update@example.com"
        )
        exercise = Exercise.objects.create(
            day=day,
            time="10:00",
            type="walk",
            kcals=100,
            duration=datetime.timedelta(minutes=15),
            distance=Decimal("1.25"),
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation UpdateExercise($id: ID!, $duration: String!) {
                    updateExercise(
                        id: $id, time: "11:30", type: "run", kcals: 200,
                        duration: $duration, distance: 2.5
                    ) { id }
                }
            """,
            variable_values={"id": str(exercise.id), "duration": duration},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert result.errors[0].message == DURATION_ERROR
        exercise.refresh_from_db()
        assert exercise.time == datetime.time(10, 0)
        assert exercise.type == "walk"
        assert exercise.kcals == 100
        assert exercise.duration == datetime.timedelta(minutes=15)
        assert exercise.distance == Decimal("1.25")


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

    def test_create_day_steps_rejects_negative_steps_before_writes(
        self, mocker
    ):
        """Create returns a stable error before attempting a negative write."""
        user, day = _create_user_with_day("negative-step-create@example.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation CreateDaySteps($dayId: Int!) {
                    createDaySteps(dayId: $dayId, steps: -1) { id }
                }
            """,
            variable_values={"dayId": day.id},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert result.errors[0].message == (
            "steps must be greater than or equal to 0"
        )
        assert not DaySteps.objects.filter(day=day).exists()

    def test_update_day_steps_rejects_negative_steps_without_changes(
        self, mocker
    ):
        """Update returns the same stable error and preserves the row."""
        user, day = _create_user_with_day("negative-step-update@example.com")
        day_steps = DaySteps.objects.create(day=day, steps=5000)
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            """
                mutation UpdateDaySteps($id: ID!) {
                    updateDaySteps(id: $id, steps: -1) { id }
                }
            """,
            variable_values={"id": str(day_steps.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert result.errors[0].message == (
            "steps must be greater than or equal to 0"
        )
        day_steps.refresh_from_db()
        assert day_steps.steps == 5000

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
