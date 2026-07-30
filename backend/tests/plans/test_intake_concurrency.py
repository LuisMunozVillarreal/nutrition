"""PostgreSQL concurrency tests for intake/day aggregate integrity."""

# pylint: disable=missing-return-doc,missing-return-type-doc

import datetime
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.models import Sum
from django.test import TransactionTestCase

from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan


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
        measurement = Measurement.objects.create(
            user=user,
            body_fat_perc=Decimal("20"),
            weight=Decimal("80"),
        )
        self.plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
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
