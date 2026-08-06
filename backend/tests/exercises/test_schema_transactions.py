"""Transaction-boundary regressions for exercise GraphQL mutations."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase

from apps.exercises import schema as exercise_schema
from apps.exercises.models import Exercise
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from config.schema import schema

User = get_user_model()


class ExerciseSchemaTransactionTests(TransactionTestCase):
    """Exercise mutation locks must execute inside the routed transaction."""

    reset_sequences = True

    def setUp(self) -> None:
        """Create one authenticated user, plan, day, and exercise."""
        self.user = User.objects.create_user(
            email="exercise-schema-transaction@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170,
        )
        measurement = Measurement.objects.create(
            user=self.user,
            weight=Decimal("80"),
            body_fat_perc=Decimal("20"),
        )
        plan = WeekPlan.objects.create(
            user=self.user,
            measurement=measurement,
            start_date=date(2026, 1, 5),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=100,
        )
        self.day = Day.objects.get(plan=plan, day_num=1)
        self.exercise = Exercise.objects.create(
            day=self.day,
            time="08:00",
            type=Exercise.EXERCISE_CYCLE,
            kcals=100,
            distance=Decimal("1.00"),
        )
        self.context = SimpleNamespace(request=SimpleNamespace(user=self.user))

    def _update(self):
        return schema.execute_sync(
            """
                mutation UpdateExercise($id: ID!) {
                    updateExercise(
                        id: $id, type: "cycle", kcals: 200,
                        time: "08:00", distance: 2
                    ) { id }
                }
            """,
            variable_values={"id": str(self.exercise.pk)},
            context_value=self.context,
        )

    def test_update_exercise_evaluates_every_lock_inside_atomic(self) -> None:
        """Structurally verify both SQLite lock evaluations."""
        original_user_lock = exercise_schema.lock_user_for_garmin_sync
        original_plan_lock = exercise_schema.lock_plan_aggregate_rows
        evaluated_locks: list[str] = []

        def checked_user_lock(*, using: str, user_id: int):
            self.assertTrue(connections[using].in_atomic_block)
            evaluated_locks.append("user")
            return original_user_lock(using=using, user_id=user_id)

        def checked_plan_lock(*, using: str, day_ids):
            self.assertTrue(connections[using].in_atomic_block)
            evaluated_locks.append("plan")
            return original_plan_lock(using=using, day_ids=day_ids)

        self.assertFalse(connection.in_atomic_block)
        with (
            patch.object(
                exercise_schema,
                "lock_user_for_garmin_sync",
                side_effect=checked_user_lock,
            ),
            patch.object(
                exercise_schema,
                "lock_plan_aggregate_rows",
                side_effect=checked_plan_lock,
            ),
        ):
            result = self._update()

        self.assertIsNone(result.errors)
        self.assertEqual(evaluated_locks, ["user", "plan"])
        self.assertFalse(connection.in_atomic_block)

    @skipUnless(
        connection.vendor == "postgresql",
        "PostgreSQL row locking is required",
    )
    def test_update_exercise_runs_from_autocommit_on_postgresql(self) -> None:
        """The real mutation may acquire row locks from autocommit callers."""
        self.assertFalse(connection.in_atomic_block)

        result = self._update()

        self.assertIsNone(result.errors)
        self.exercise.refresh_from_db()
        self.assertEqual(self.exercise.kcals, 200)
        self.assertEqual(self.exercise.distance, Decimal("2.00"))
