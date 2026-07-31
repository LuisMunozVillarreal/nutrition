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

from apps.foods import cupboard_locks
from apps.foods import deletion as food_deletion
from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)
from apps.foods.signals.handlers import cupboard as cupboard_handlers
from apps.measurements.models import Measurement
from apps.plans.models import Intake, WeekPlan
from apps.plans.models import intake as intake_model
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
        original_deletion_lock = food_deletion.lock_nutrition_deletion

        def pause_manual_after_lock(authoritative_item):
            manual_locked.set()
            if not release_manual.wait(timeout=10):
                raise RuntimeError("timed out releasing manual cupboard lock")
            return original_get_linked(authoritative_item)

        def observe_linked_lock(instance, using):
            linked_lock_attempted.set()
            return original_lock(instance, using)

        def observe_deletion_lock(targets, using):
            linked_lock_attempted.set()
            return original_deletion_lock(targets, using)

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
            patch(
                "apps.foods.deletion.lock_nutrition_deletion",
                side_effect=observe_deletion_lock,
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
class RecipeCupboardFanoutConcurrencyTests(TransactionTestCase):
    """Exercise cooked recipes sharing multiple cupboard rows."""

    reset_sequences = True

    def setUp(self):
        """Create two recipes with the same ingredients in opposite orders."""
        self.user = User.objects.create_user(
            email="recipe-fanout@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        self.products = [
            FoodProduct.objects.create(
                name=f"Shared stock {index}",
                size=Decimal("100"),
                size_unit="g",
                num_servings=10,
            )
            for index in range(2)
        ]
        self.servings = [
            Serving.objects.create(
                food=product,
                serving_size=Decimal("10"),
                serving_unit="g",
            )
            for product in self.products
        ]
        self.items = [
            CupboardItem.objects.create(
                owner=self.user,
                food=product,
                purchased_at=timezone.now(),
            )
            for product in self.products
        ]
        first_recipe = Recipe.objects.create(
            name="Forward recipe", size=1, size_unit="count", num_servings=1
        )
        second_recipe = Recipe.objects.create(
            name="Reverse recipe", size=1, size_unit="count", num_servings=1
        )
        for serving in self.servings:
            RecipeIngredient.objects.create(
                recipe=first_recipe, food=serving, num_servings=1
            )
        for serving in reversed(self.servings):
            RecipeIngredient.objects.create(
                recipe=second_recipe, food=serving, num_servings=1
            )
        self.recipe_ids = (first_recipe.pk, second_recipe.pk)

    def test_opposite_recipe_orders_lock_shared_cupboard_rows_without_deadlock(
        self,
    ):
        """Both fan-outs complete after synchronizing their first legacy lock."""
        ready = threading.Barrier(2)
        first_legacy_locks = threading.Barrier(2)
        threads_seen = set()
        threads_seen_guard = threading.Lock()
        original_lock = (
            cupboard_handlers._lock_cupboard_item  # pylint: disable=protected-access
        )

        def synchronize_first_legacy_lock(instance, using):
            locked_item = original_lock(instance, using)
            thread_id = threading.get_ident()
            with threads_seen_guard:
                is_first = thread_id not in threads_seen
                threads_seen.add(thread_id)
            if is_first:
                first_legacy_locks.wait(timeout=10)
            return locked_item

        def cook(recipe_id):
            close_old_connections()
            try:
                recipe = Recipe.objects.get(pk=recipe_id)
                user = User.objects.get(pk=self.user.pk)
                ready.wait(timeout=10)
                CupboardItem.objects.create(
                    owner=user,
                    food=recipe,
                    purchased_at=timezone.now(),
                )
                return id(connection.connection)
            finally:
                close_old_connections()

        with (
            patch(
                "apps.foods.signals.handlers.cupboard._lock_cupboard_item",
                side_effect=synchronize_first_legacy_lock,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            futures = [
                executor.submit(cook, recipe_id)
                for recipe_id in self.recipe_ids
            ]
            connection_ids = [future.result(timeout=20) for future in futures]

        self.assertNotEqual(*connection_ids)
        self.assertEqual(
            CupboardItem.objects.filter(
                owner=self.user, food_id__in=self.recipe_ids
            ).count(),
            2,
        )
        self.assertEqual(
            CupboardItemConsumption.objects.filter(
                item__in=self.items
            ).count(),
            4,
        )
        for item in self.items:
            item.refresh_from_db()
            self.assertEqual(item.consumed_perc, Decimal("20"))


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
        original_plan_locks = intake_model.lock_plan_aggregate_rows

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
                intake_model,
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


@skipUnless(
    connection.vendor == "postgresql"
    and connection.features.has_select_for_update,
    "PostgreSQL row locks are required",
)
class IntakeCupboardGlobalOrderConcurrencyTests(TransactionTestCase):
    """Exercise opposite intake swaps and cascades across shared stock rows."""

    reset_sequences = True

    def setUp(self):
        """Create two independent plan hierarchies sharing two cupboard rows."""
        self.user = User.objects.create_user(
            email="cupboard-global-order@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=self.user,
            body_fat_perc=Decimal("20"),
            weight=Decimal("80"),
        )
        self.plans = [
            WeekPlan.objects.create(
                user=self.user,
                measurement=measurement,
                start_date=datetime.date(2026, 2, 2 + 7 * index),
                protein_g_kg=Decimal("1.8"),
                fat_perc=Decimal("25"),
                deficit=100,
            )
            for index in range(2)
        ]
        self.days = [plan.days.get(day_num=1) for plan in self.plans]
        self.products = [
            FoodProduct.objects.create(
                name=f"Global-order stock {index}",
                size=Decimal("100"),
                size_unit="g",
                num_servings=10,
            )
            for index in range(2)
        ]
        self.servings = [
            product.servings.create(
                serving_size=Decimal("10"), serving_unit="g"
            )
            for product in self.products
        ]
        self.items = [
            CupboardItem.objects.create(
                owner=self.user,
                food=product,
                purchased_at=timezone.now(),
            )
            for product in self.products
        ]

    @staticmethod
    def _run_competing(first, second):
        ready = threading.Barrier(2)

        def run(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '15s'")
                ready.wait(timeout=10)
                operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(run, worker) for worker in (first, second)
            ]
            for future in futures:
                future.result(timeout=20)

    def test_opposite_intake_food_swaps_lock_both_items_by_pk(self):
        """A-to-B and B-to-A swaps cannot deadlock on old/new item order."""
        intakes = [
            Intake.objects.create(
                day=day,
                food=serving,
                meal=Intake.MEAL_LUNCH,
            )
            for day, serving in zip(self.days, self.servings, strict=True)
        ]
        before_cupboard = threading.Barrier(2)
        original_lock = intake_model.lock_intake_cupboard_rows

        def synchronize_before_cupboard(*args, **kwargs):
            before_cupboard.wait(timeout=10)
            return original_lock(*args, **kwargs)

        def swap(intake_id, serving_id):
            stale = Intake.objects.get(pk=intake_id)
            stale.food_id = serving_id
            stale.save()

        with patch.object(
            intake_model,
            "lock_intake_cupboard_rows",
            new=synchronize_before_cupboard,
        ):
            self._run_competing(
                lambda: swap(intakes[0].pk, self.servings[1].pk),
                lambda: swap(intakes[1].pk, self.servings[0].pk),
            )

        for item in self.items:
            item.refresh_from_db()
            self.assertEqual(item.consumed_perc, Decimal("10"))
        self.assertEqual(
            list(
                CupboardItemConsumption.objects.order_by(
                    "intake_id"
                ).values_list("item_id", flat=True)
            ),
            [self.items[1].pk, self.items[0].pk],
        )

    def _assert_opposite_cascades_complete(self, roots):
        for day in self.days:
            for serving in reversed(self.servings):
                Intake.objects.create(
                    day=day,
                    food=serving,
                    meal=Intake.MEAL_LUNCH,
                )
        before_cupboard = threading.Barrier(2)
        original_lock = cupboard_locks.lock_cupboard_items

        def synchronize_before_cupboard(*args, **kwargs):
            before_cupboard.wait(timeout=10)
            return original_lock(*args, **kwargs)

        def delete(model, row_id):
            model.objects.get(pk=row_id).delete()

        with patch.object(
            cupboard_locks,
            "lock_cupboard_items",
            new=synchronize_before_cupboard,
        ):
            self._run_competing(
                lambda: delete(type(roots[0]), roots[0].pk),
                lambda: delete(type(roots[1]), roots[1].pk),
            )

        self.assertFalse(Intake.objects.exists())
        for item in self.items:
            item.refresh_from_db()
            self.assertEqual(item.consumed_perc, Decimal("0"))

    def test_opposite_day_cascades_lock_complete_item_sets_by_pk(self):
        """Day cascades prelock shared cupboard sets without inversion."""
        self._assert_opposite_cascades_complete(self.days)

    def test_opposite_week_cascades_lock_complete_item_sets_by_pk(self):
        """Weekly plan cascades prelock shared cupboard sets without inversion."""
        self._assert_opposite_cascades_complete(self.plans)
