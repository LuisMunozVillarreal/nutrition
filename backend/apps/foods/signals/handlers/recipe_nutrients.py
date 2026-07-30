"""Recipe aggregate locking, validation, and signal handlers."""

from decimal import Decimal
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.db.models.signals import post_delete, pre_delete, pre_save
from django.dispatch import receiver
from pint.errors import DimensionalityError, UndefinedUnitError

from apps.foods.models import Recipe, RecipeIngredient
from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.foods.models.units import UNIT_CONTAINER, UNIT_SERVING, UREG

CONTEXTUAL_UNITS = {UNIT_CONTAINER, UNIT_SERVING}


def synchronize_recipe_aggregates(
    source: Recipe, target: Recipe | None
) -> bool:
    """Copy authoritative aggregates to a caller-held recipe instance.

    Args:
        source (Recipe): authoritative locked recipe instance.
        target (Recipe | None): caller-held recipe instance, when cached.

    Returns:
        bool: whether a matching target was synchronized.
    """
    if target is None or target.pk != source.pk:
        return False
    for field in NUTRIENT_LIST + ["size"]:
        setattr(target, field, getattr(source, field))
    return True


def _size_in_recipe_unit(
    ingredient: RecipeIngredient, recipe: Recipe
) -> Decimal:
    """Convert an immutable ingredient size snapshot to the recipe unit."""
    source_unit = ingredient.effective_size_snapshot_unit
    if source_unit in CONTEXTUAL_UNITS or recipe.size_unit in CONTEXTUAL_UNITS:
        raise ValidationError("Recipe ingredient size units must be concrete")
    try:
        converted = UREG.Quantity(ingredient.size, source_unit).to(
            recipe.size_unit
        )
    except (DimensionalityError, UndefinedUnitError) as error:
        raise ValidationError(
            "Recipe ingredient size unit is incompatible with the recipe unit"
        ) from error
    return Decimal(str(converted.magnitude))


def lock_recipe_ingredients(
    recipe_ids: Iterable[int], using: str
) -> tuple[dict[int, Recipe], list[RecipeIngredient]]:
    """Lock authoritative recipes, then their ingredients in stable key order.

    Args:
        recipe_ids (Iterable[int]): recipes affected by the mutation.
        using (str): database alias used by the mutation.

    Returns:
        tuple: locked recipes by ID and their locked ingredients.
    """
    ordered_ids = sorted(set(recipe_ids))
    recipes = list(
        Recipe.objects.select_for_update()
        .using(using)
        .filter(pk__in=ordered_ids)
        .order_by("pk")
    )
    ingredients = list(
        RecipeIngredient.objects.select_for_update()
        .using(using)
        .filter(recipe_id__in=ordered_ids)
        .select_related("food__food")
        .order_by("recipe_id", "pk")
    )
    return {recipe.pk: recipe for recipe in recipes}, ingredients


def validate_recipe_ingredient_size(
    ingredient: RecipeIngredient, recipe: Recipe
) -> None:
    """Reject an ingredient that cannot contribute to an enabled aggregate.

    Args:
        ingredient (RecipeIngredient): proposed ingredient state.
        recipe (Recipe): authoritative target recipe.
    """
    if recipe.nutrients_from_ingredients:
        _size_in_recipe_unit(ingredient, recipe)


def recompute_recipe_nutrients(recipe: Recipe, using: str) -> None:
    """Rebuild enabled aggregates from the authoritative ingredient snapshots.

    Args:
        recipe (Recipe): authoritative locked recipe instance.
        using (str): database alias used by the mutation.
    """
    if not recipe.nutrients_from_ingredients:
        return
    totals = {nutrient: Decimal("0") for nutrient in NUTRIENT_LIST}
    total_size = Decimal("0")
    ingredients = (
        RecipeIngredient.objects.using(using)
        .filter(recipe_id=recipe.pk)
        .select_related("food__food")
        .order_by("pk")
    )
    for ingredient in ingredients:
        total_size += _size_in_recipe_unit(ingredient, recipe)
        for nutrient in NUTRIENT_LIST:
            totals[nutrient] += getattr(ingredient, nutrient) or 0
    recipe.size = total_size
    for nutrient, value in totals.items():
        setattr(recipe, nutrient, value)
    recipe.save(using=using, update_fields=NUTRIENT_LIST + ["size"])


def increase_recipe_nutrients(
    sender: RecipeIngredient,  # pylint: disable=unused-argument
    instance: RecipeIngredient,
    using: str = "default",
    **kwargs: Any,
) -> None:
    """Compatibility entry point that performs an authoritative rebuild.

    Args:
        sender (RecipeIngredient): signal sender.
        instance (RecipeIngredient): changed ingredient instance.
        using (str): database alias used by the mutation.
        kwargs (Any): additional signal arguments.
    """
    recompute_recipe_nutrients(instance.recipe, using)


@receiver(pre_delete, sender=RecipeIngredient)
def lock_recipe_ingredient_deletion(
    sender: RecipeIngredient,  # pylint: disable=unused-argument
    instance: RecipeIngredient,
    using: str,
    **kwargs: Any,
) -> None:
    """Serialize deletion with every other mutation of the same recipe.

    Args:
        sender (RecipeIngredient): signal sender.
        instance (RecipeIngredient): ingredient being deleted.
        using (str): database alias used by the mutation.
        kwargs (Any): additional signal arguments.
    """
    # pylint: disable=protected-access
    aggregate_observer = instance._state.fields_cache.get("recipe")
    # pylint: enable=protected-access
    setattr(instance, "_aggregate_observer", aggregate_observer)
    recipes, _ingredients = lock_recipe_ingredients(
        [instance.recipe_id], using
    )
    setattr(instance, "_locked_recipe", recipes[instance.recipe_id])


@receiver(post_delete, sender=RecipeIngredient)
def decrease_recipe_nutrients(
    sender: RecipeIngredient,  # pylint: disable=unused-argument
    instance: RecipeIngredient,
    using: str,
    **kwargs: Any,
) -> None:
    """Rebuild the recipe after the locked ingredient deletion.

    Args:
        sender (RecipeIngredient): signal sender.
        instance (RecipeIngredient): deleted ingredient instance.
        using (str): database alias used by the mutation.
        kwargs (Any): additional signal arguments.
    """
    recipe = getattr(instance, "_locked_recipe", instance.recipe)
    recompute_recipe_nutrients(recipe, using)
    synchronize_recipe_aggregates(
        recipe, getattr(instance, "_aggregate_observer", None)
    )


@receiver(pre_save, sender=Recipe)
def calculate_recipe_nutrients(
    sender: Recipe,  # pylint: disable=unused-argument
    instance: Recipe,
    using: str,
    **kwargs: Any,
) -> None:
    """Build aggregates when enabling ingredient mode or changing recipe unit.

    Args:
        sender (Recipe): signal sender.
        instance (Recipe): recipe being saved.
        using (str): database alias used by the mutation.
        kwargs (Any): additional signal arguments.
    """
    if instance.pk is None or not instance.nutrients_from_ingredients:
        return
    db_recipe = Recipe.objects.using(using).get(pk=instance.pk)
    if (
        db_recipe.nutrients_from_ingredients
        and db_recipe.size_unit == instance.size_unit
    ):
        return
    totals = {nutrient: Decimal("0") for nutrient in NUTRIENT_LIST}
    total_size = Decimal("0")
    for ingredient in (
        RecipeIngredient.objects.using(using)
        .filter(recipe_id=instance.pk)
        .select_related("food__food")
        .order_by("pk")
    ):
        total_size += _size_in_recipe_unit(ingredient, instance)
        for nutrient in NUTRIENT_LIST:
            totals[nutrient] += getattr(ingredient, nutrient) or 0
    instance.size = total_size
    for nutrient, value in totals.items():
        setattr(instance, nutrient, value)
