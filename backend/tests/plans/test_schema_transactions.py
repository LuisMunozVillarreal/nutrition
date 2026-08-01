"""Transaction-boundary regressions for plan GraphQL mutations."""

from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase

from apps.measurements.models import Measurement
from apps.plans import schema as plan_schema
from apps.plans.models import WeekPlan
from config.schema import schema

User = get_user_model()


class PlanSchemaTransactionTests(TransactionTestCase):
    """Plan mutation locks must execute inside the routed transaction."""

    reset_sequences = True

    def setUp(self) -> None:
        """Create one authenticated user and starting measurement."""
        self.user = User.objects.create_user(
            email="plan-schema-transaction@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170,
        )
        self.measurement = Measurement.objects.create(
            user=self.user,
            weight=Decimal("80"),
            body_fat_perc=Decimal("20"),
        )
        self.context = SimpleNamespace(request=SimpleNamespace(user=self.user))

    def _create_plan(self):
        return schema.execute_sync(
            """
                mutation CreatePlan($measurementId: Int!) {
                    createWeekPlan(
                        startDate: "2026-01-05",
                        proteinGKg: 1.8,
                        fatPerc: 25,
                        deficit: 100,
                        measurementId: $measurementId
                    ) { id }
                }
            """,
            variable_values={"measurementId": self.measurement.pk},
            context_value=self.context,
        )

    def test_create_week_plan_evaluates_user_lock_inside_atomic(self) -> None:
        """Structurally verify the SQLite schema lock evaluation."""
        original_user_lock = plan_schema.lock_user_for_garmin_sync
        evaluated_locks: list[str] = []

        def checked_user_lock(*, using: str, user_id: int):
            self.assertTrue(connections[using].in_atomic_block)
            evaluated_locks.append("user")
            return original_user_lock(using=using, user_id=user_id)

        self.assertFalse(connection.in_atomic_block)
        with patch.object(
            plan_schema,
            "lock_user_for_garmin_sync",
            side_effect=checked_user_lock,
        ):
            result = self._create_plan()

        self.assertIsNone(result.errors)
        self.assertEqual(evaluated_locks, ["user"])
        self.assertFalse(connection.in_atomic_block)

    def test_update_week_plan_evaluates_aggregate_lock_inside_atomic(
        self,
    ) -> None:
        """Structurally verify the routed SQLite aggregate lock."""
        created = self._create_plan()
        self.assertIsNone(created.errors)
        plan_id = created.data["createWeekPlan"]["id"]
        original_plan_lock = plan_schema.lock_plan_aggregate_rows
        evaluated_locks: list[str] = []

        def checked_plan_lock(*, using: str, plan_ids, day_ids):
            self.assertTrue(connections[using].in_atomic_block)
            evaluated_locks.append("plan")
            return original_plan_lock(
                using=using,
                plan_ids=plan_ids,
                day_ids=day_ids,
            )

        self.assertFalse(connection.in_atomic_block)
        with patch.object(
            plan_schema,
            "lock_plan_aggregate_rows",
            side_effect=checked_plan_lock,
        ):
            result = schema.execute_sync(
                """
                    mutation UpdatePlan($id: ID!) {
                        updateWeekPlan(
                            id: $id, proteinGKg: 2, fatPerc: 25, deficit: 100
                        ) { id }
                    }
                """,
                variable_values={"id": plan_id},
                context_value=self.context,
            )

        self.assertIsNone(result.errors)
        self.assertEqual(evaluated_locks, ["plan"])
        self.assertFalse(connection.in_atomic_block)

    @skipUnless(
        connection.vendor == "postgresql",
        "PostgreSQL row locking is required",
    )
    def test_create_week_plan_runs_from_autocommit_on_postgresql(self) -> None:
        """The real mutation may acquire its user lock from autocommit callers."""
        self.assertFalse(connection.in_atomic_block)

        result = self._create_plan()

        self.assertIsNone(result.errors)
        self.assertTrue(WeekPlan.objects.filter(user=self.user).exists())
