"""PostgreSQL concurrency tests for manual and linked cupboard writes."""

import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    FoodProduct,
)
from apps.foods.signals.handlers import cupboard as cupboard_handlers
from apps.measurements.models import Measurement
from apps.plans import locks as plan_locks
from apps.plans.models import Intake, WeekPlan
from config.schema import schema

User = get_user_model()


@skipUnless(
    connection.vendor == "postgresql"
    and connection.features.has_select_for_update,
    "PostgreSQL row locks are required",
)
class CupboardManualLinkedConcurrencyTests(TransactionTestCase):
    """Prove manual totals serialize with every linked-write shape."""

    reset_sequences = True

    def setUp(self):
        """Create stock with a deterministic ten-percent serving."""
        self.user = User.objects.create_user(
            email="cupboard-race@test.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        self.product = FoodProduct.objects.create(
            name="Concurrent stock",
            size=Decimal("100"),
            size_unit="g",
            num_servings=1,
        )
        self.serving = self.product.servings.create(
            serving_size=Decimal("10"),
            serving_unit="g",
        )
        self.item = CupboardItem.objects.create(
            owner=self.user,
            food=self.product,
            purchased_at=timezone.now(),
            consumed_perc=Decimal("20"),
        )

    # pylint: disable-next=too-many-locals
    def _run_manual_first_race(self, prepare_linked, mutate_linked):
        """Hold the manual row lock while a stale linked writer attempts it."""
        ready = threading.Barrier(2)
        manual_locked = threading.Event()
        linked_lock_attempted = threading.Event()
        release_manual = threading.Event()
        original_get_linked = cupboard_handlers.get_linked_consumed_perc
        original_lock = (
            cupboard_handlers._lock_cupboard_item  # pylint: disable=protected-access
        )

        def pause_manual_after_lock(authoritative_item):
            manual_locked.set()
            if not release_manual.wait(timeout=10):
                raise RuntimeError("timed out releasing manual cupboard lock")
            return original_get_linked(authoritative_item)

        def observe_linked_lock(instance, using):
            linked_lock_attempted.set()
            return original_lock(instance, using)

        def update_manual():
            close_old_connections()
            try:
                thread_user = User.objects.get(pk=self.user.pk)
                context = SimpleNamespace(
                    request=SimpleNamespace(user=thread_user)
                )
                ready.wait(timeout=10)
                result = schema.execute_sync(
                    """
                    mutation UpdateItem($id: ID!) {
                        updateCupboardItem(id: $id, consumedPerc: 50) {
                            consumedPerc
                        }
                    }
                    """,
                    variable_values={"id": str(self.item.pk)},
                    context_value=context,
                )
                if result.errors:
                    raise AssertionError(str(result.errors))
                return id(connection.connection), Decimal(
                    str(result.data["updateCupboardItem"]["consumedPerc"])
                )
            finally:
                close_old_connections()

        def write_linked():
            close_old_connections()
            try:
                stale_linked = prepare_linked()
                connection_id = id(connection.connection)
                ready.wait(timeout=10)
                if not manual_locked.wait(timeout=10):
                    raise RuntimeError("manual cupboard lock was not acquired")
                mutate_linked(stale_linked)
                return connection_id
            finally:
                close_old_connections()

        with (
            patch(
                "apps.foods.schema.get_linked_consumed_perc",
                side_effect=pause_manual_after_lock,
            ),
            patch(
                "apps.foods.signals.handlers.cupboard._lock_cupboard_item",
                side_effect=observe_linked_lock,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            manual_future = executor.submit(update_manual)
            linked_future = executor.submit(write_linked)
            self.assertTrue(linked_lock_attempted.wait(timeout=10))
            release_manual.set()
            manual_connection, requested_total = manual_future.result(
                timeout=10
            )
            linked_connection = linked_future.result(timeout=10)

        self.assertNotEqual(manual_connection, linked_connection)
        self.assertEqual(requested_total, Decimal("50"))

    def test_manual_update_serializes_before_linked_create(self):
        """A later create adds its ten percent after the requested total."""

        def prepare():
            return (
                CupboardItem.objects.get(pk=self.item.pk),
                self.product.servings.get(pk=self.serving.pk),
            )

        def create_link(stale):
            item, serving = stale
            CupboardItemConsumption.objects.create(item=item, serving=serving)

        self._run_manual_first_race(prepare, create_link)

        self.item.refresh_from_db()
        self.assertEqual(self.item.manual_consumed_perc, Decimal("50"))
        self.assertEqual(self.item.consumed_perc, Decimal("60"))
        self.assertEqual(self.item.consumptions.count(), 1)

    def test_manual_update_serializes_before_linked_update(self):
        """A later update applies its ten-percent delta after the requested total."""
        consumption = CupboardItemConsumption.objects.create(
            item=self.item,
            serving=self.serving,
        )

        def prepare():
            return CupboardItemConsumption.objects.select_related("item").get(
                pk=consumption.pk
            )

        def update_link(stale):
            stale.num_servings = Decimal("2")
            stale.consumed_amount = None
            stale.consumed_unit = None
            stale.save()

        self._run_manual_first_race(prepare, update_link)

        self.item.refresh_from_db()
        consumption.refresh_from_db()
        self.assertEqual(self.item.manual_consumed_perc, Decimal("40"))
        self.assertEqual(self.item.consumed_perc, Decimal("60"))
        self.assertEqual(consumption.consumed_amount, Decimal("20"))

    def test_manual_update_serializes_before_linked_delete(self):
        """A later delete subtracts its ten percent after the requested total."""
        consumption = CupboardItemConsumption.objects.create(
            item=self.item,
            serving=self.serving,
        )

        def prepare():
            return CupboardItemConsumption.objects.select_related("item").get(
                pk=consumption.pk
            )

        def delete_link(stale):
            stale.delete()

        self._run_manual_first_race(prepare, delete_link)

        self.item.refresh_from_db()
        self.assertEqual(self.item.manual_consumed_perc, Decimal("40"))
        self.assertEqual(self.item.consumed_perc, Decimal("40"))
        self.assertFalse(self.item.consumptions.exists())


@skipUnless(
    connection.vendor == "postgresql"
    and connection.features.has_select_for_update,
    "PostgreSQL row locks are required",
)
class ServingCascadeConcurrencyTests(TransactionTestCase):
    """Prove serving collection uses intake-compatible aggregate locks."""

    reset_sequences = True

    def setUp(self):
        """Create one intake linked to stock and a plan aggregate."""
        self.user = User.objects.create_user(
            email="serving-cascade@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=self.user,
            body_fat_perc=Decimal("20"),
            weight=Decimal("80"),
        )
        self.plan = WeekPlan.objects.create(
            user=self.user,
            measurement=measurement,
            start_date=datetime.date(2026, 1, 5),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=100,
        )
        self.day = self.plan.days.get(day_num=1)
        self.product = FoodProduct.objects.create(
            name="Cascade stock",
            size=Decimal("100"),
            size_unit="g",
            nutritional_info_size=Decimal("100"),
            energy_kcal=Decimal("100"),
            num_servings=1,
        )
        self.serving = self.product.servings.create(
            serving_size=Decimal("10"),
            serving_unit="g",
        )
        self.item = CupboardItem.objects.create(
            owner=self.user,
            food=self.product,
            purchased_at=timezone.now(),
            consumed_perc=Decimal("20"),
        )
        self.intake = Intake.objects.create(
            day=self.day,
            food=self.serving,
            meal=Intake.MEAL_LUNCH,
            num_servings=Decimal("1"),
        )

    def test_intake_write_and_serving_delete_do_not_deadlock(self):
        """Deletion waits on plan/day before touching the shared cupboard row."""
        writer_before_cupboard = threading.Event()
        deletion_plan_lock_attempted = threading.Event()
        release_writer = threading.Event()
        original_cupboard_lock = CupboardItem.objects.select_for_update
        original_plan_locks = plan_locks.lock_plan_aggregate_rows

        def pause_writer_before_cupboard(*args, **kwargs):
            if (
                threading.current_thread().name == "intake-write"
                and not writer_before_cupboard.is_set()
            ):
                writer_before_cupboard.set()
                if not release_writer.wait(timeout=10):
                    raise RuntimeError("timed out releasing intake writer")
            return original_cupboard_lock(*args, **kwargs)

        def observe_deletion_plan_lock(*args, **kwargs):
            if threading.current_thread().name == "serving-delete":
                deletion_plan_lock_attempted.set()
            return original_plan_locks(*args, **kwargs)

        def update_intake():
            threading.current_thread().name = "intake-write"
            close_old_connections()
            try:
                stale = Intake.objects.get(pk=self.intake.pk)
                stale.num_servings = Decimal("2")
                stale.save()
                return id(connection.connection)
            finally:
                close_old_connections()

        def delete_serving():
            threading.current_thread().name = "serving-delete"
            close_old_connections()
            try:
                if not writer_before_cupboard.wait(timeout=10):
                    raise RuntimeError("intake writer did not reach cupboard")
                stale = type(self.serving).objects.get(pk=self.serving.pk)
                stale.delete()
                return id(connection.connection)
            finally:
                close_old_connections()

        with (
            patch.object(
                CupboardItem.objects,
                "select_for_update",
                side_effect=pause_writer_before_cupboard,
            ),
            patch.object(
                plan_locks,
                "lock_plan_aggregate_rows",
                side_effect=observe_deletion_plan_lock,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            writer_future = executor.submit(update_intake)
            deletion_future = executor.submit(delete_serving)
            self.assertTrue(deletion_plan_lock_attempted.wait(timeout=10))
            release_writer.set()
            writer_connection = writer_future.result(timeout=20)
            deletion_connection = deletion_future.result(timeout=20)

        self.assertNotEqual(writer_connection, deletion_connection)
        self.assertFalse(
            type(self.serving).objects.filter(pk=self.serving.pk).exists()
        )
        self.assertFalse(Intake.objects.filter(pk=self.intake.pk).exists())
        self.item.refresh_from_db()
        self.day.refresh_from_db()
        self.plan.refresh_from_db()
        self.assertEqual(self.item.manual_consumed_perc, Decimal("20"))
        self.assertEqual(self.item.consumed_perc, Decimal("20"))
        self.assertEqual(self.day.energy_kcal, Decimal("0"))
        self.assertEqual(self.plan.energy_kcal, Decimal("0"))
