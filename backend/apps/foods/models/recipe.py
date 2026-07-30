"""Recipe models module."""

# pylint: disable=cyclic-import

from decimal import Decimal
from typing import Any, cast

from django.db import models, router, transaction

from .food import Food
from .nutrients import NUTRIENT_LIST, Nutrients
from .units import UNIT_CHOICES, UNIT_CONTAINER, UNIT_SERVING


class Recipe(Food):
    """Recipe models class."""

    description = models.TextField(
        blank=True,
    )

    nutrients_from_ingredients = models.BooleanField(
        default=False,
        verbose_name="Calculate nutrients from ingredients",
    )

    @property
    def num_ingredients(self) -> int:
        """Get number of ingredients.

        Returns:
            str: number of ingredients.
        """
        return self.ingredients.count()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Persist recalculated aggregates when ingredient mode is enabled.

        Args:
            args (Any): positional model save arguments.
            kwargs (Any): keyword model save arguments.
        """
        if (
            self.pk is not None
            and self.nutrients_from_ingredients
            and kwargs.get("update_fields") is not None
        ):
            kwargs["update_fields"] = set(kwargs["update_fields"]) | set(
                NUTRIENT_LIST + ["size"]
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return f"{self.name} ({self.num_servings}s)"


class RecipeIngredient(Nutrients):
    """RecipeIngredient models class."""

    recipe = models.ForeignKey(
        "foods.Recipe",
        on_delete=models.CASCADE,
        related_name="ingredients",
    )

    food = models.ForeignKey(
        "foods.Serving",
        on_delete=models.CASCADE,
        related_name="recipes",
    )

    num_servings = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=1,
    )

    size_snapshot = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        editable=False,
        help_text="Total ingredient size captured from its serving when saved.",
    )

    size_snapshot_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        null=True,
        editable=False,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return (
            f"{self.recipe.name} - {str(self.food)}"
            f" {self.food.serving_size * self.num_servings} "
            f"({self.food.serving_unit})"
        )

    @property
    def size(self) -> Decimal:
        """Get the immutable total size of this ingredient.

        Returns:
            Decimal: captured or lazily resolved total size.
        """
        if self.size_snapshot is not None:
            return self.size_snapshot
        return self.food.size * self.num_servings

    @property
    def effective_size_snapshot_unit(self) -> str:
        """Return the snapshot unit, lazily resolving expansion-era rows.

        Returns:
            str: concrete unit associated with the ingredient size.
        """
        if self.size_snapshot_unit is not None:
            return self.size_snapshot_unit
        if self.food.serving_unit in (UNIT_CONTAINER, UNIT_SERVING):
            return self.food.food.size_unit
        return self.food.serving_unit

    def _prepare_snapshots(
        self,
        previous: "RecipeIngredient | None",
        update_fields: set[str] | None,
    ) -> set[str] | None:
        """Prepare immutable amount, unit, and nutrient snapshot fields."""
        serving_changed = previous is None or (
            previous.food_id != self.food_id
            or previous.num_servings != self.num_servings
        )
        snapshot_fields: set[str] = set()
        current_size = self.food.size * self.num_servings
        current_unit = (
            self.food.food.size_unit
            if self.food.serving_unit in (UNIT_CONTAINER, UNIT_SERVING)
            else self.food.serving_unit
        )
        if serving_changed or self.size_snapshot is None:
            self.size_snapshot = current_size
            snapshot_fields.add("size_snapshot")
        if serving_changed or self.size_snapshot_unit is None:
            self.size_snapshot_unit = current_unit
            snapshot_fields.add("size_snapshot_unit")
        if serving_changed:
            for nutrient in NUTRIENT_LIST:
                value = getattr(self.food, nutrient) or 0
                setattr(self, nutrient, value * self.num_servings)
            snapshot_fields.update(NUTRIENT_LIST)
        return (
            None if update_fields is None else update_fields | snapshot_fields
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Lock, mutate, and authoritatively rebuild recipe aggregates atomically.

        Args:
            args (Any): positional model save arguments.
            kwargs (Any): keyword model save arguments.
        """
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        aggregate_observer = cast(
            Recipe | None, self._state.fields_cache.get("recipe")
        )
        previous_recipe_id = None
        if self.pk is not None:
            previous_recipe_id = (
                type(self)
                .objects.using(using)
                .filter(pk=self.pk)
                .values_list("recipe_id", flat=True)
                .first()
            )
        recipe_ids = {self.recipe_id}
        if previous_recipe_id is not None:
            recipe_ids.add(previous_recipe_id)

        from apps.foods.signals.handlers.recipe_nutrients import (
            lock_recipe_ingredients,
            recompute_recipe_nutrients,
            synchronize_recipe_aggregates,
            validate_recipe_ingredient_size,
        )

        with transaction.atomic(using=using):
            recipes, ingredients = lock_recipe_ingredients(recipe_ids, using)
            previous = next(
                (
                    ingredient
                    for ingredient in ingredients
                    if ingredient.pk == self.pk
                ),
                None,
            )
            target_recipe = recipes[self.recipe_id]
            self.recipe = target_recipe
            update_fields = kwargs.get("update_fields")
            prepared_fields = self._prepare_snapshots(
                previous,
                None if update_fields is None else set(update_fields),
            )
            if prepared_fields is not None:
                kwargs["update_fields"] = prepared_fields
            validate_recipe_ingredient_size(self, target_recipe)
            super().save(*args, **kwargs)
            for recipe_id in sorted(recipe_ids):
                recompute_recipe_nutrients(recipes[recipe_id], using)
        target_recipe = recipes[self.recipe_id]
        if aggregate_observer is not None and synchronize_recipe_aggregates(
            target_recipe, aggregate_observer
        ):
            self.recipe = aggregate_observer
