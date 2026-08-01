"""PostgreSQL concurrency regressions for exercise aggregates."""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.exercises import schema as exercise_schema
from apps.exercises.models import Exercise
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from config.schema import schema

User = get_user_model()


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL row locks are required for this concurrency suite",
)
class ExerciseConcurrencyTests(TransactionTestCase):
    """GraphQL stale caller updates should not silently clobber."""

    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        """Create deterministic user/day fixture shared by tests."""
        super().setUpClass()
        cls._user = User.objects.create_user(
            email="exercise-concurrency@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170,
        )
        cls._measurement = Measurement.objects.create(
            user=cls._user,
            weight=Decimal("80"),
            body_fat_perc=Decimal("20"),
        )
        cls._plan = WeekPlan.objects.create(
            user=cls._user,
            measurement=cls._measurement,
            start_date="2026-01-05",
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=100,
        )
        day = Day.objects.filter(plan=cls._plan).first()
        assert day is not None
        cls._day = day

    def _run_workers(self, first, second):
        """Run two workers in parallel on dedicated connections."""
        ready = threading.Barrier(2)

        def run(operation):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(run, operation)
                for operation in (first, second)
            ]
            return [future.result(timeout=20) for future in futures]

    def test_stale_update_fields_do_not_overwrite(self):
        """Schema updates with stale caller state must preserve fields."""
        exercise = Exercise.objects.create(
            day=self._day,
            time="08:00",
            type=Exercise.EXERCISE_CYCLE,
            kcals=100,
            duration=None,
            distance=Decimal("1.00"),
        )

        barrier = threading.Barrier(2)
        original_get = exercise_schema.Exercise.objects.get

        def tracked_get(*args, **kwargs):
            obj = original_get(*args, **kwargs)
            if str(kwargs.get("pk")) == str(exercise.pk):
                barrier.wait(timeout=10)
            return obj

        def update_kcals():
            context = SimpleNamespace(request=SimpleNamespace(user=self._user))
            result = schema.execute_sync(
                """
                    mutation UpdateExercise(
                        $id: ID!, $type: String!, $kcals: Int!,
                        $time: String!, $distance: Float
                    ) {
                        updateExercise(
                            id: $id, type: $type, kcals: $kcals,
                            time: $time, distance: $distance
                        ) { kcals distance }
                    }
                """,
                variable_values={
                    "id": str(exercise.pk),
                    "type": Exercise.EXERCISE_CYCLE,
                    "kcals": 200,
                    "time": "08:00",
                    "distance": 1.0,
                },
                context_value=context,
            )
            return result

        def update_distance():
            context = SimpleNamespace(request=SimpleNamespace(user=self._user))
            result = schema.execute_sync(
                """
                    mutation UpdateExercise(
                        $id: ID!, $type: String!, $kcals: Int!,
                        $time: String!, $distance: Float
                    ) {
                        updateExercise(
                            id: $id, type: $type, kcals: $kcals,
                            time: $time, distance: $distance
                        ) { kcals distance }
                    }
                """,
                variable_values={
                    "id": str(exercise.pk),
                    "type": Exercise.EXERCISE_CYCLE,
                    "kcals": 100,
                    "time": "08:00",
                    "distance": 2.0,
                },
                context_value=context,
            )
            return result

        with patch.object(
            exercise_schema.Exercise.objects,
            "get",
            side_effect=tracked_get,
        ):
            result_first, result_second = self._run_workers(
                update_kcals,
                update_distance,
            )

        assert result_first.errors is None
        assert result_second.errors is None

        exercise.refresh_from_db()
        assert exercise.kcals == 200
        assert exercise.distance == Decimal("2.00")
