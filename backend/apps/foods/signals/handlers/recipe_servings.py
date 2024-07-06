"""food app signal handlers for recipe servings module."""

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.foods.models import Food, Recipe, Serving
from apps.foods.models.units import UNIT_SERVING


@receiver(post_save, sender=Recipe)
def add_recipe_serving(
    sender: Recipe,  # pylint: disable=unused-argument
    instance: Recipe,
    created: bool,
    **kwargs: Any,
):
    """Add serving to the recipe.

    Args:
        sender (Recipe): signal sender.
        instance (Recipe): instance to be saved.
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    # pylint: disable=duplicate-code
    if not created:
        return

    food = Food.objects.get(id=instance.id)

    Serving.objects.create(
        food=food,
        size=1,
        unit=UNIT_SERVING,
    )


@receiver(post_save, sender=Recipe)
def update_recipe_serving_nutrients(
    sender: Recipe,  # pylint: disable=unused-argument
    instance: Recipe,
    created: bool,
    **kwargs: Any,
):
    """Update serving nutrients of the recipe.

    Args:
        sender (Recipe): signal sender.
        instance (Recipe): instance to be saved.
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    if created:
        return

    serving = Serving.objects.get(food=instance)
    serving.save()
