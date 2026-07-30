"""PostgreSQL concurrency regressions for recipe ingredient aggregates."""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

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
