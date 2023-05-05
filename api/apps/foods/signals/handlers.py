"""food app signal handlers module."""


from typing import Any

from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from apps.foods.models import Recipe, RecipeIngredient
from apps.foods.models.nutrients import NUTRIENT_LIST


@receiver(pre_save, sender=RecipeIngredient)
def increase_recipe_nutrients(
    sender: RecipeIngredient,  # pylint: disable=unused-argument
    instance: RecipeIngredient,
    **kwargs: dict[Any, Any],
) -> None:
    """Increase the recipe nutrients.

    Args:
        sender (RecipeIngredient): signal sender.
        instance (RecipeIngredient): instance to be saved.
        kwargs (dict[Any, Any]): keyword arguments.
    """
    recipe = instance.recipe
    if not recipe.nutrients_from_ingredients:
        return

    created = instance.id is None
    ingredient = instance

    for nutrient in NUTRIENT_LIST:
        old_ingredient_value = 0
        new_ingredient_value = getattr(ingredient, nutrient)
        if not new_ingredient_value:
            continue

        if not created:
            db_ingredient = RecipeIngredient.objects.get(id=instance.id)
            old_ingredient_value = getattr(db_ingredient, nutrient)

        diff = new_ingredient_value - old_ingredient_value
        recipe_value = getattr(recipe, nutrient) or 0
        setattr(recipe, nutrient, recipe_value + diff)

    recipe.save()


@receiver(pre_delete, sender=RecipeIngredient)
def decrease_recipe_nutrients(
    sender: RecipeIngredient,  # pylint: disable=unused-argument
    instance: RecipeIngredient,
    **kwargs: dict[Any, Any],
) -> None:
    """Decrease the recipe nutrients.

    Args:
        sender (RecipeIngredient): signal sender.
        instance (RecipeIngredient): instance to be saved.
        kwargs (dict[Any, Any]): keyword arguments.
    """
    recipe = instance.recipe
    if not recipe.nutrients_from_ingredients:
        return

    ingredient = instance

    for nutrient in NUTRIENT_LIST:
        recipe_value = getattr(recipe, nutrient)
        ingredient_value = getattr(ingredient, nutrient)
        if ingredient_value:
            setattr(recipe, nutrient, recipe_value - ingredient_value)

    recipe.save()


@receiver(pre_save, sender=Recipe)
def calculate_recipe_nutrients(
    sender: Recipe,  # pylint: disable=unused-argument
    instance: Recipe,
    **kwargs: dict[Any, Any],
) -> None:
    """Calculate recipe nutrients.

    Args:
        sender (Recipe): signal sender.
        instance (Recipe): instance to be saved.
        kwargs (dict[Any, Any]): keyword arguments.
    """
    if instance.id is None:
        return

    recipe = instance
    if not recipe.nutrients_from_ingredients:
        return

    db_recipe = Recipe.objects.get(id=recipe.id)
    if db_recipe.nutrients_from_ingredients:
        return

    for nutrient in NUTRIENT_LIST:
        recipe_value = 0
        for ingredient in recipe.ingredients.all():
            value = ingredient.get_portion_for(ingredient.food, nutrient)
            if not value:
                continue

            recipe_value += value

        setattr(recipe, nutrient, recipe_value)
