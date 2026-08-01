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
@pytest.mark.parametrize(
    ("operation", "distance"),
    [("create", 0.01), ("update", 99999999.99)],
)
def test_exercise_mutations_accept_two_decimal_boundaries(
    mocker, operation, distance
):
    """Exercise create and update accept supported distance boundaries."""
    user, day = _create_user_with_day(
        f"exercise-boundary-{operation}@example.com"
    )
    exercise = Exercise.objects.create(
        day=day, time="10:00", type="walk", kcals=100, distance=1
    )
    context = mocker.Mock()
    context.request.user = user
    if operation == "create":
        exercise.delete()
        mutation = """
            mutation Boundary($dayId: Int!, $distance: Float) {
                createExercise(
                    dayId: $dayId, type: "walk", kcals: 100,
                    distance: $distance
                ) { id }
            }
        """
        variables = {"dayId": day.id, "distance": distance}
    else:
        mutation = """
            mutation Boundary($id: ID!, $distance: Float) {
                updateExercise(
                    id: $id, type: "walk", kcals: 100,
                    distance: $distance
                ) { id }
            }
        """
        variables = {"id": str(exercise.id), "distance": distance}

    result = schema.execute_sync(
        mutation, variable_values=variables, context_value=context
    )

    assert result.errors is None
    persisted = Exercise.objects.get(
        pk=result.data[
            "createExercise" if operation == "create" else "updateExercise"
        ]["id"]
    )
    assert persisted.distance == Decimal(str(distance))


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


@pytest.mark.django_db
class TestExerciseOwnershipIsolation:
    """Prove exercise and step resolvers cannot cross user boundaries."""

    @staticmethod
    def _context(mocker, user):
        """Build an authenticated GraphQL context for a concrete user."""
        context = mocker.Mock()
        context.request.user = user
        return context

    def test_single_record_queries_hide_another_users_records(self, mocker):
        """Single-record queries return null for records owned by another user."""
        requesting_user, _ = _create_user_with_day(
            "isolation-query@example.com"
        )
        _, owned_day = _create_user_with_day(
            "isolation-query-owner@example.com"
        )
        exercise = Exercise.objects.create(
            day=owned_day, time="10:00", type="walk", kcals=100
        )
        day_steps = DaySteps.objects.create(day=owned_day, steps=5000)

        result = schema.execute_sync(
            """
                query OtherUserRecords($exerciseId: ID!, $dayStepsId: ID!) {
                    exercise(id: $exerciseId) { id }
                    daySteps(id: $dayStepsId) { id }
                }
            """,
            variable_values={
                "exerciseId": str(exercise.id),
                "dayStepsId": str(day_steps.id),
            },
            context_value=self._context(mocker, requesting_user),
        )

        assert result.errors is None
        assert result.data == {"exercise": None, "daySteps": None}

    def test_day_steps_list_returns_only_requesting_users_records(
        self, mocker
    ):
        """The day-steps list excludes rows owned by every other user."""
        requesting_user, requesting_day = _create_user_with_day(
            "isolation-list@example.com"
        )
        _, other_day = _create_user_with_day(
            "isolation-list-owner@example.com"
        )
        own_steps = DaySteps.objects.create(day=requesting_day, steps=1234)
        DaySteps.objects.create(day=other_day, steps=9876)

        result = schema.execute_sync(
            """
                query RequestingUserSteps {
                    dayStepsList { id steps }
                }
            """,
            context_value=self._context(mocker, requesting_user),
        )

        assert result.errors is None
        assert result.data == {
            "dayStepsList": [{"id": str(own_steps.id), "steps": 1234}]
        }

    @pytest.mark.parametrize(
        "case",
        [
            (
                "createExercise",
                """
                    mutation OtherUserExercise($dayId: Int!) {
                        createExercise(
                            dayId: $dayId, type: "walk", kcals: 100
                        ) { id }
                    }
                """,
                "Day not found",
                Exercise,
            ),
            (
                "createDaySteps",
                """
                    mutation OtherUserSteps($dayId: Int!) {
                        createDaySteps(dayId: $dayId, steps: 5000) { id }
                    }
                """,
                "Day not found",
                DaySteps,
            ),
        ],
    )
    def test_creates_reject_another_users_day(self, mocker, case):
        """Create mutations cannot attach records to another user's day."""
        field, mutation, expected_error, model = case
        requesting_user, _ = _create_user_with_day(
            f"isolation-{field}@example.com"
        )
        _, owned_day = _create_user_with_day(
            f"isolation-{field}-owner@example.com"
        )
        initial_count = model.objects.filter(day=owned_day).count()

        result = schema.execute_sync(
            mutation,
            variable_values={"dayId": owned_day.id},
            context_value=self._context(mocker, requesting_user),
        )

        assert result.errors is not None
        assert result.errors[0].message == expected_error
        assert model.objects.filter(day=owned_day).count() == initial_count

    def test_updates_reject_another_users_records_without_changes(
        self, mocker
    ):
        """Update mutations preserve records owned by another user."""
        requesting_user, _ = _create_user_with_day(
            "isolation-update@example.com"
        )
        _, owned_day = _create_user_with_day(
            "isolation-update-owner@example.com"
        )
        exercise = Exercise.objects.create(
            day=owned_day, time="10:00", type="walk", kcals=100
        )
        day_steps = DaySteps.objects.create(day=owned_day, steps=5000)
        context = self._context(mocker, requesting_user)

        exercise_result = schema.execute_sync(
            """
                mutation OtherUserExercise($id: ID!) {
                    updateExercise(
                        id: $id, type: "run", kcals: 999
                    ) { id }
                }
            """,
            variable_values={"id": str(exercise.id)},
            context_value=context,
        )
        steps_result = schema.execute_sync(
            """
                mutation OtherUserSteps($id: ID!) {
                    updateDaySteps(id: $id, steps: 999) { id }
                }
            """,
            variable_values={"id": str(day_steps.id)},
            context_value=context,
        )

        assert exercise_result.errors is not None
        assert exercise_result.errors[0].message == "Exercise not found"
        assert steps_result.errors is not None
        assert steps_result.errors[0].message == "Day steps not found"
        exercise.refresh_from_db()
        day_steps.refresh_from_db()
        assert (exercise.type, exercise.kcals) == ("walk", 100)
        assert day_steps.steps == 5000

    def test_deletes_reject_another_users_records_without_changes(
        self, mocker
    ):
        """Delete mutations cannot remove records owned by another user."""
        requesting_user, _ = _create_user_with_day(
            "isolation-delete@example.com"
        )
        _, owned_day = _create_user_with_day(
            "isolation-delete-owner@example.com"
        )
        exercise = Exercise.objects.create(
            day=owned_day, time="10:00", type="walk", kcals=100
        )
        day_steps = DaySteps.objects.create(day=owned_day, steps=5000)
        context = self._context(mocker, requesting_user)

        exercise_result = schema.execute_sync(
            """
                mutation OtherUserExercise($id: ID!) {
                    deleteExercise(id: $id)
                }
            """,
            variable_values={"id": str(exercise.id)},
            context_value=context,
        )
        steps_result = schema.execute_sync(
            """
                mutation OtherUserSteps($id: ID!) {
                    deleteDaySteps(id: $id)
                }
            """,
            variable_values={"id": str(day_steps.id)},
            context_value=context,
        )

        assert exercise_result.errors is not None
        assert exercise_result.errors[0].message == "Exercise not found"
        assert steps_result.errors is not None
        assert steps_result.errors[0].message == "Day steps not found"
        assert Exercise.objects.filter(pk=exercise.id).exists()
        assert DaySteps.objects.filter(pk=day_steps.id).exists()
