"""PostgreSQL concurrency regressions for recipe ingredient aggregates."""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.foods import recipe_locks
from apps.foods.models import FoodProduct, Recipe, RecipeIngredient, Serving


@skipUnless(
    connection.vendor == "postgresql"
    and connection.features.has_select_for_update,
    "PostgreSQL row locks are required",
)
class RecipeIngredientConcurrencyTests(TransactionTestCase):
    """Exercise independent transactions racing on one authoritative recipe."""

    @staticmethod
    def _run_concurrently(*workers):
        ready = threading.Barrier(len(workers))

        def run(worker):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                worker()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = [executor.submit(run, worker) for worker in workers]
            for future in futures:
                future.result(timeout=20)

    @staticmethod
    def _recipe() -> Recipe:
        return Recipe.objects.create(
            name="Concurrent recipe",
            nutrients_from_ingredients=True,
            size=0,
            size_unit="g",
        )

    @staticmethod
    def _serving(amount: str, unit: str) -> Serving:
        product = FoodProduct.objects.create(
            name=f"Concurrent {amount}{unit}",
            size=Decimal(amount),
            size_unit=unit,
            nutritional_info_unit=unit,
        )
        return Serving.objects.create(
            food=product,
            serving_size=Decimal(amount),
            serving_unit=unit,
        )

    def test_concurrent_mixed_unit_adds_keep_both_contributions(self):
        """Concurrent kg and g inserts cannot overwrite one another's total."""
        recipe = self._recipe()
        gram_serving = self._serving("100", "g")
        kilogram_serving = self._serving("1", "kg")

        def add(serving_id):
            RecipeIngredient.objects.create(
                recipe=Recipe.objects.get(pk=recipe.pk),
                food=Serving.objects.get(pk=serving_id),
            )

        self._run_concurrently(
            lambda: add(gram_serving.pk),
            lambda: add(kilogram_serving.pk),
        )

        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients.count(), 2)
        self.assertEqual(recipe.size, Decimal("1100"))

    def test_refresh_then_concurrent_write_is_not_restored_by_full_save(self):
        """A refreshed baseline preserves a later write from another connection."""
        recipe = self._recipe()
        Recipe.objects.filter(pk=recipe.pk).update(num_servings=Decimal("1"))
        stale = Recipe.objects.get(pk=recipe.pk)
        Recipe.objects.filter(pk=recipe.pk).update(num_servings=Decimal("2"))
        stale.refresh_from_db()
        concurrent_done = threading.Event()

        def concurrent_write():
            Recipe.objects.filter(pk=recipe.pk).update(
                num_servings=Decimal("3")
            )
            concurrent_done.set()

        def unrelated_save():
            if not concurrent_done.wait(timeout=10):
                raise RuntimeError("concurrent recipe write did not finish")
            stale.name = "Concurrent refreshed rename"
            stale.save()

        self._run_concurrently(concurrent_write, unrelated_save)

        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Concurrent refreshed rename")
        self.assertEqual(recipe.num_servings, Decimal("3"))

    def test_recipe_update_loaded_before_ingredient_write_recomputes_latest_state(
        self,
    ):
        """A stale recipe update cannot overwrite a later ingredient contribution."""
        recipe = self._recipe()
        serving = self._serving("100", "g")
        serving.energy_kcal = Decimal("50")
        serving.save()
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe, food=serving
        )
        update_loaded = threading.Event()
        ingredient_done = threading.Event()

        def update_recipe():
            stale = Recipe.objects.get(pk=recipe.pk)
            stale.name = "Concurrent rename"
            stale.size = Decimal("1")
            stale.size_unit = "kg"
            stale.nutritional_info_unit = "kg"
            stale.num_servings = Decimal("4")
            stale.energy_kcal = Decimal("1")
            update_loaded.set()
            if not ingredient_done.wait(timeout=10):
                raise RuntimeError("ingredient update did not finish")
            stale.save()

        def update_ingredient():
            if not update_loaded.wait(timeout=10):
                raise RuntimeError("recipe update did not load")
            current = RecipeIngredient.objects.get(pk=ingredient.pk)
            current.num_servings = Decimal("2")
            current.save(update_fields=["num_servings"])
            ingredient_done.set()

        self._run_concurrently(update_recipe, update_ingredient)

        recipe.refresh_from_db()
        self.assertEqual(recipe.name, "Concurrent rename")
        self.assertEqual(recipe.size_unit, "kg")
        self.assertEqual(recipe.num_servings, Decimal("4.0"))
        self.assertEqual(recipe.size, Decimal("0.2"))
        self.assertEqual(recipe.energy_kcal, Decimal("100.00"))
        generated_serving = recipe.servings.get()
        self.assertEqual(generated_serving.energy_kcal, Decimal("25.00"))

    def test_concurrent_updates_recompute_every_committed_contribution(self):
        """Independent ingredient updates cannot lose either new quantity."""
        recipe = self._recipe()
        serving = self._serving("100", "g")
        ingredients = [
            RecipeIngredient.objects.create(recipe=recipe, food=serving)
            for _ in range(2)
        ]

        def update(ingredient_id, quantity):
            ingredient = RecipeIngredient.objects.get(pk=ingredient_id)
            ingredient.num_servings = Decimal(quantity)
            ingredient.save(update_fields=["num_servings"])

        self._run_concurrently(
            lambda: update(ingredients[0].pk, "2"),
            lambda: update(ingredients[1].pk, "3"),
        )

        recipe.refresh_from_db()
        self.assertEqual(recipe.size, Decimal("500"))

    def test_concurrent_deletes_recompute_only_remaining_ingredients(self):
        """Concurrent removals cannot restore a deleted contribution."""
        recipe = self._recipe()
        serving = self._serving("100", "g")
        ingredients = [
            RecipeIngredient.objects.create(recipe=recipe, food=serving)
            for _ in range(3)
        ]

        def delete(ingredient_id):
            RecipeIngredient.objects.get(pk=ingredient_id).delete()

        self._run_concurrently(
            lambda: delete(ingredients[0].pk),
            lambda: delete(ingredients[1].pk),
        )

        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients.count(), 1)
        self.assertEqual(recipe.size, Decimal("100"))

    def test_concurrent_moves_recompute_the_intermediate_recipe(self):
        """R1-to-R2/R3 races restart after observing a newer current owner."""
        recipes = [self._recipe() for _ in range(3)]
        serving = self._serving("100", "g")
        ingredient = RecipeIngredient.objects.create(
            recipe=recipes[0], food=serving
        )
        stale_moves = [
            RecipeIngredient.objects.get(pk=ingredient.pk) for _ in range(2)
        ]
        first_lock_attempt = threading.Barrier(2)
        seen_threads = set()
        seen_guard = threading.Lock()
        original_lock = recipe_locks.lock_recipe_ingredients

        def synchronize_after_stale_owner_sample(*args, **kwargs):
            thread_id = threading.get_ident()
            with seen_guard:
                first_attempt = thread_id not in seen_threads
                seen_threads.add(thread_id)
            if first_attempt:
                first_lock_attempt.wait(timeout=10)
            return original_lock(*args, **kwargs)

        def move(stale, destination):
            stale.recipe_id = destination.pk
            stale.save(update_fields=["recipe"])

        with patch.object(
            recipe_locks,
            "lock_recipe_ingredients",
            new=synchronize_after_stale_owner_sample,
        ):
            self._run_concurrently(
                lambda: move(stale_moves[0], recipes[1]),
                lambda: move(stale_moves[1], recipes[2]),
            )

        ingredient.refresh_from_db()
        for recipe in recipes:
            recipe.refresh_from_db()
            expected_size = sum(
                (
                    row.size
                    for row in RecipeIngredient.objects.filter(recipe=recipe)
                ),
                Decimal("0"),
            )
            self.assertEqual(recipe.size, expected_size)
        self.assertIn(ingredient.recipe_id, (recipes[1].pk, recipes[2].pk))
