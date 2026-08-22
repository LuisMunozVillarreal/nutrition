"""Transaction-boundary regressions for measurement GraphQL mutations."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase

from apps.measurements import schema as measurement_schema
from apps.measurements.models import Measurement
from apps.plans.models import WeekPlan
from config.schema import schema

User = get_user_model()


class MeasurementSchemaTransactionTests(TransactionTestCase):
    """Measurement mutation locks must use the routed transaction."""

    def test_update_measurement_evaluates_aggregate_lock_inside_atomic(
        self,
    ) -> None:
        """Structurally verify SQLite aggregate lock evaluation."""
        user = User.objects.create_user(
            email="measurement-schema-transaction@example.com",
            password="password123",
            date_of_birth=date(2000, 1, 1),
            height=170,
        )
        measurement = Measurement.objects.create(
            user=user,
            weight=Decimal("80"),
            body_fat_perc=Decimal("20"),
        )
        WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=date(2026, 1, 5),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=100,
        )
        context = SimpleNamespace(request=SimpleNamespace(user=user))
        original_plan_lock = measurement_schema.lock_plan_aggregate_rows
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
            measurement_schema,
            "lock_plan_aggregate_rows",
            side_effect=checked_plan_lock,
        ):
            result = schema.execute_sync(
                """
                    mutation UpdateMeasurement($id: ID!) {
                        updateMeasurement(id: $id, weight: 81, bodyFatPerc: 19) {
                            id
                        }
                    }
                """,
                variable_values={"id": str(measurement.pk)},
                context_value=context,
            )

        self.assertIsNone(result.errors)
        self.assertEqual(evaluated_locks, ["plan"])
        self.assertFalse(connection.in_atomic_block)
