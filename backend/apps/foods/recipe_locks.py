"""Canonical row-lock bundles for recipe aggregate mutations and deletions."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from django.apps import apps


@dataclass(frozen=True)
class RecipeAggregateLocks:
    """Canonical Recipe then RecipeIngredient locks held by a writer."""

    using: str
    recipes_by_pk: dict[int, Any]
    ingredients: tuple[Any, ...]

    def covers(self, recipe_id: int, using: str) -> bool:
        """Return whether this bundle owns the requested recipe hierarchy.

        Args:
            recipe_id (int): Recipe primary key that must be covered.
            using (str): Database alias on which locks must be held.

        Returns:
            bool: Whether the requested hierarchy is locked by this bundle.
        """
        return self.using == using and recipe_id in self.recipes_by_pk


_active_recipe_aggregate_locks: ContextVar[RecipeAggregateLocks | None] = (
    ContextVar("active_recipe_aggregate_locks", default=None)
)


def get_recipe_aggregate_locks() -> RecipeAggregateLocks | None:
    """Return locks active for the current bulk/cascade deletion context.

    Returns:
        RecipeAggregateLocks | None: Active lock bundle, if any.
    """
    return _active_recipe_aggregate_locks.get()


@contextmanager
def activate_recipe_aggregate_locks(
    locks: RecipeAggregateLocks,
) -> Iterator[None]:
    """Expose pre-collector locks to RecipeIngredient deletion signals.

    Args:
        locks (RecipeAggregateLocks): Bundle held by the outer transaction.
    """
    token = _active_recipe_aggregate_locks.set(locks)
    try:
        yield
    finally:
        _active_recipe_aggregate_locks.reset(token)


def lock_recipe_ingredients(
    recipe_ids: Iterable[int], using: str
) -> tuple[dict[int, Any], list[Any]]:
    """Lock authoritative recipes, then their ingredients in stable key order.

    Args:
        recipe_ids (Iterable[int]): Recipes affected by the mutation.
        using (str): Database alias used by the mutation.

    Returns:
        tuple: Locked recipes by ID and their locked ingredients.
    """
    recipe_model = apps.get_model("foods", "Recipe")
    ingredient_model = apps.get_model("foods", "RecipeIngredient")
    ordered_ids = sorted(set(recipe_ids))
    recipes = list(
        recipe_model.objects.select_for_update()
        .using(using)
        .filter(pk__in=ordered_ids)
        .order_by("pk")
    )
    ingredients = list(
        ingredient_model.objects.select_for_update()
        .using(using)
        .filter(recipe_id__in=ordered_ids)
        .select_related("food__food")
        .order_by("recipe_id", "pk")
    )
    return {recipe.pk: recipe for recipe in recipes}, ingredients


def lock_recipe_aggregate_rows(
    recipe_ids: Iterable[int], using: str
) -> RecipeAggregateLocks:
    """Return one canonical lock bundle for all affected recipes.

    Args:
        recipe_ids (Iterable[int]): Affected recipe primary keys.
        using (str): Database alias used by the mutation.

    Returns:
        RecipeAggregateLocks: Locked recipe hierarchies.
    """
    recipes, ingredients = lock_recipe_ingredients(recipe_ids, using)
    return RecipeAggregateLocks(using, recipes, tuple(ingredients))
