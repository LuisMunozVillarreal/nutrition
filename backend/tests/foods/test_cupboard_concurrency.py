"""PostgreSQL concurrency tests for manual and linked cupboard writes."""

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
