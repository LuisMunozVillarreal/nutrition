"""Recipe aggregate locking, validation, and signal handlers."""

from decimal import Decimal
from typing import Any, Iterable, cast

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, pre_delete, pre_save
from django.dispatch import receiver
from pint.errors import DimensionalityError, UndefinedUnitError

from apps.foods.models import Recipe, RecipeIngredient
from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.foods.models.units import UNIT_CONTAINER, UNIT_SERVING, UREG
from apps.foods.recipe_locks import (
    get_recipe_aggregate_locks,
    lock_recipe_aggregate_rows,
)

CONTEXTUAL_UNITS = {UNIT_CONTAINER, UNIT_SERVING}


def _camel_case(field_name: str) -> str:
    """Return the stable GraphQL-style name used in validation messages."""
    first, *rest = field_name.split("_")
    return first + "".join(part.title() for part in rest)


def validate_derived_decimal(
    value: Decimal,
    destination_model: type[Recipe] | type[RecipeIngredient],
    field_name: str,
    scope: str,
) -> Decimal:
    """Validate a derived value against its exact persisted decimal field.

    Args:
        value (Decimal): Derived value to validate.
        destination_model (type): Model whose decimal field will persist it.
        field_name (str): Destination decimal field name.
        scope (str): Stable validation-message prefix.

    Returns:
        Decimal: Validated normalized value.

    Raises:
        ValidationError: If the value exceeds destination-field precision.
    """
    field = cast(
        models.DecimalField, destination_model._meta.get_field(field_name)
    )
    normalized = value.normalize() if value else Decimal("0")
    try:
        return field.clean(normalized, None)
    except ValidationError as error:
        label = _camel_case(field_name)
        if field_name == "size_snapshot":
            label = "sizeSnapshot"
        raise ValidationError(
            f"{scope} {label} exceeds supported precision"
        ) from error


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


def apply_recipe_ingredient_totals(
    recipe: Recipe, ingredients: Iterable[RecipeIngredient]
) -> None:
    """Apply authoritative ingredient snapshots to an enabled recipe instance.

    Args:
        recipe (Recipe): Recipe receiving authoritative totals.
        ingredients (Iterable[RecipeIngredient]): Locked ingredient snapshots.
    """
    if not recipe.nutrients_from_ingredients:
        return
    totals = {nutrient: Decimal("0") for nutrient in NUTRIENT_LIST}
    total_size = Decimal("0")
    for ingredient in ingredients:
        size_contribution = validate_derived_decimal(
            _size_in_recipe_unit(ingredient, recipe),
            Recipe,
            "size",
            "Recipe",
        )
        total_size = validate_derived_decimal(
            total_size + size_contribution,
            Recipe,
            "size",
            "Recipe",
        )
        for nutrient in NUTRIENT_LIST:
            contribution = validate_derived_decimal(
                getattr(ingredient, nutrient) or Decimal("0"),
                Recipe,
                nutrient,
                "Recipe",
            )
            totals[nutrient] = validate_derived_decimal(
                totals[nutrient] + contribution,
                Recipe,
                nutrient,
                "Recipe",
            )
    recipe.size = total_size
    for nutrient, value in totals.items():
        setattr(recipe, nutrient, value)


def recompute_recipe_nutrients(recipe: Recipe, using: str) -> None:
    """Rebuild enabled aggregates from the authoritative ingredient snapshots.

    Args:
        recipe (Recipe): authoritative locked recipe instance.
        using (str): database alias used by the mutation.
    """
    if not recipe.nutrients_from_ingredients:
        return
    ingredients = list(
        RecipeIngredient.objects.using(using)
        .filter(recipe_id=recipe.pk)
        .select_related("food__food")
        .order_by("pk")
    )
    apply_recipe_ingredient_totals(recipe, ingredients)
    recipe.save(
        using=using,
        update_fields=NUTRIENT_LIST + ["size"],
        _skip_aggregate_lock=True,
    )


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
    locks = get_recipe_aggregate_locks()
    if locks is None or not locks.covers(instance.recipe_id, using):
        locks = lock_recipe_aggregate_rows([instance.recipe_id], using)
    setattr(
        instance, "_locked_recipe", locks.recipes_by_pk[instance.recipe_id]
    )


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
    ingredients = list(
        RecipeIngredient.objects.using(using)
        .filter(recipe_id=instance.pk)
        .select_related("food__food")
        .order_by("pk")
    )
    apply_recipe_ingredient_totals(instance, ingredients)
