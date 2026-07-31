"""PostgreSQL concurrency tests for intake/day aggregate integrity."""

# pylint: disable=missing-return-doc,missing-return-type-doc
# pylint: disable=too-many-locals,import-outside-toplevel

import datetime
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.db.models import Sum
from django.db.models.query import QuerySet
from django.test import TransactionTestCase

from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan
from config.schema import schema


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL row locking is required for this concurrency suite",
)
class IntakeAggregateConcurrencyTests(TransactionTestCase):
    """Exercise competing writes on separate database connections."""

    reset_sequences = True

    def setUp(self):
        """Create an isolated plan/day without sharing thread connections."""
        user = get_user_model().objects.create_user(
            email="intake-concurrency@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170,
        )
        self.user = user
        self.measurement = Measurement.objects.create(
            user=user,
            body_fat_perc=Decimal("20"),
            weight=Decimal("80"),
        )
        self.plan = WeekPlan.objects.create(
            user=user,
            measurement=self.measurement,
            start_date=datetime.date(2026, 1, 5),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=100,
        )
        self.day = self.plan.days.get(day_num=1)

    def _assert_stored_totals_match_rows(self):
        """Compare stored day/plan values with a fresh intake aggregation."""
        totals = Intake.objects.filter(
            day_id=self.day.pk, processed=True
        ).aggregate(
            **{
                nutrient: Sum(nutrient, default=Decimal("0"))
                for nutrient in NUTRIENT_LIST
            }
        )
        self.day.refresh_from_db()
        self.plan.refresh_from_db()
        for nutrient, total in totals.items():
            self.assertEqual(getattr(self.day, nutrient), total)
        plan_energy = Day.objects.filter(plan=self.plan).aggregate(
            total=Sum("energy_kcal", default=Decimal("0"))
        )["total"]
        self.assertEqual(self.plan.energy_kcal, plan_energy)
        expected_completed = not self.plan.days.filter(
            completed=False
        ).exists()
        self.assertEqual(self.plan.completed, expected_completed)

    def _run_competing(self, first, second):
        """Start two operations together, each on its own Django connection."""
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

    def test_concurrent_creates_do_not_lose_day_updates(self):
        """Creates serialize on Day even though neither has an Intake to lock."""

        def create(energy):
            def operation():
                Intake.objects.create(
                    day_id=self.day.pk,
                    food=None,
                    meal=Intake.MEAL_LUNCH,
                    energy_kcal=energy,
                    protein_g=energy / 10,
                )
                return "created"

            return operation

        results = self._run_competing(
            create(Decimal("100")), create(Decimal("200"))
        )

        self.assertEqual(results, ["created", "created"])
        self.assertEqual(Intake.objects.filter(day=self.day).count(), 2)
        self._assert_stored_totals_match_rows()

    def test_concurrent_update_and_delete_leave_fresh_totals(self):
        """An update/delete race cannot preserve a deleted intake contribution."""
        intake = Intake.objects.create(
            day=self.day,
            food=None,
            meal=Intake.MEAL_LUNCH,
            energy_kcal=Decimal("100"),
            protein_g=Decimal("10"),
        )

        loaded = threading.Barrier(2)

        def update():
            stale = Intake.objects.get(pk=intake.pk)
            loaded.wait(timeout=10)
            stale.energy_kcal = Decimal("250")
            stale.protein_g = Decimal("25")
            try:
                stale.save()
            except Intake.DoesNotExist:
                return "deleted-first"
            return "updated"

        def delete():
            stale = Intake.objects.get(pk=intake.pk)
            loaded.wait(timeout=10)
            stale.delete()
            return "deleted"

        results = self._run_competing(update, delete)

        self.assertIn(results[0], ("updated", "deleted-first"))
        self.assertEqual(results[1], "deleted")
        self.assertFalse(Intake.objects.filter(pk=intake.pk).exists())
        self._assert_stored_totals_match_rows()

    def test_opposing_bulk_deletes_with_interleaved_ids_do_not_deadlock(self):
        """Bulk collectors globally lock opposing plan/day sets before signals."""
        second_plan = WeekPlan.objects.create(
            user=self.user,
            measurement=self.measurement,
            start_date=datetime.date(2026, 1, 12),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=100,
        )
        days = sorted(
            (self.day, second_plan.days.get(day_num=1)), key=lambda row: row.pk
        )

        def create(day, energy):
            return Intake.objects.create(
                day=day,
                food=None,
                meal=Intake.MEAL_LUNCH,
                energy_kcal=Decimal(energy),
            )

        sentinels = [create(day, "10") for day in days]
        # Ascending IDs make A visit low/high days and B visit high/low days.
        first_a = create(days[0], "100")
        first_b = create(days[1], "200")
        second_b = create(days[0], "300")
        second_a = create(days[1], "400")
        delete_ids = (
            (first_a.pk, second_a.pk),
            (first_b.pk, second_b.pk),
        )
        lock_attempt = threading.Barrier(2)
        from apps.plans.models import intake as intake_module

        original_lock = intake_module.lock_plan_aggregate_rows

        def interleave_before_global_lock(*args, **kwargs):
            lock_attempt.wait(timeout=10)
            return original_lock(*args, **kwargs)

        def bulk_delete(ids):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '5s'")
                    cursor.execute("SET LOCAL statement_timeout = '15s'")
                Intake.objects.filter(pk__in=ids).delete()
            return "deleted"

        with patch.object(
            intake_module,
            "lock_plan_aggregate_rows",
            new=interleave_before_global_lock,
        ):
            results = self._run_competing(
                lambda: bulk_delete(delete_ids[0]),
                lambda: bulk_delete(delete_ids[1]),
            )

        self.assertEqual(results, ["deleted", "deleted"])
        self.assertFalse(
            Intake.objects.filter(
                pk__in=[pk for ids in delete_ids for pk in ids]
            ).exists()
        )
        self.assertEqual(
            set(Intake.objects.values_list("pk", flat=True)),
            {row.pk for row in sentinels},
        )
        for day in days:
            day.refresh_from_db()
            day.plan.refresh_from_db()
            self.assertEqual(day.energy_kcal, Decimal("10.00"))
            self.assertEqual(day.plan.energy_kcal, Decimal("10.00"))

    def test_measurement_update_and_intake_create_do_not_deadlock(self):
        """Cross-feature writes serialize plan-before-day and keep fresh totals."""
        role = threading.local()
        measurement_has_plan = threading.Event()
        release_measurement = threading.Event()
        intake_reached_plan_save = threading.Event()
        original_fetch_all = (
            QuerySet._fetch_all  # pylint: disable=protected-access
        )
        original_plan_save = WeekPlan.save

        def pause_measurement_after_plan_lock(queryset):
            original_fetch_all(queryset)
            if (
                getattr(role, "name", None) == "measurement"
                and queryset.model is WeekPlan
                and queryset.query.select_for_update
            ):
                measurement_has_plan.set()
                if not release_measurement.wait(timeout=10):
                    raise TimeoutError("measurement lock interleave timed out")

        def observe_intake_plan_save(plan, *args, **kwargs):
            if getattr(role, "name", None) == "intake":
                intake_reached_plan_save.set()
            return original_plan_save(plan, *args, **kwargs)

        def update_measurement():
            role.name = "measurement"
            context = SimpleNamespace(request=SimpleNamespace(user=self.user))
            return schema.execute_sync(
                """
                    mutation UpdateMeasurement($id: ID!) {
                        updateMeasurement(
                            id: $id, bodyFatPerc: 18, weight: 82
                        ) { id }
                    }
                """,
                variable_values={"id": str(self.measurement.pk)},
                context_value=context,
            )

        def create_intake():
            role.name = "intake"
            return Intake.objects.create(
                day_id=self.day.pk,
                food=None,
                meal=Intake.MEAL_LUNCH,
                energy_kcal=Decimal("125"),
            ).pk

        with (
            patch.object(
                QuerySet, "_fetch_all", new=pause_measurement_after_plan_lock
            ),
            patch.object(WeekPlan, "save", new=observe_intake_plan_save),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            measurement_future = executor.submit(update_measurement)
            self.assertTrue(measurement_has_plan.wait(timeout=10))
            intake_future = executor.submit(create_intake)

            # Under the old Day-then-WeekPlan order the intake reaches plan.save
            # while holding Day, completing the PostgreSQL deadlock cycle.
            intake_reached_plan_save.wait(timeout=1)
            release_measurement.set()
            measurement_result = measurement_future.result(timeout=20)
            intake_future.result(timeout=20)

        self.assertIsNone(measurement_result.errors)
        self.measurement.refresh_from_db()
        self.day.refresh_from_db()
        self.assertEqual(self.measurement.weight, Decimal("82.0"))
        self.assertEqual(self.day.energy_kcal, Decimal("125.00"))
        self.assertEqual(self.day.protein_g_goal, Decimal("147.60"))
        self._assert_stored_totals_match_rows()
