"""food app signal handlers for food product."""


from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.foods.models import Food, FoodProduct, Serving
from apps.foods.models.units import UNIT_CONTAINER, UNIT_SERVING


@receiver(post_save, sender=FoodProduct)
def add_default_servings(
    sender: FoodProduct,  # pylint: disable=unused-argument
    instance: FoodProduct,
    created: bool,
    **kwargs: Any,
):
    """Add default servings.

    Args:
        sender (FoodProduct): signal sender.
        instance (FoodProduct): instance to be saved.
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    if not created:
        return

    food = Food.objects.get(id=instance.id)

    Serving.objects.create(
        food=food,
        size=food.nutritional_info_size,
        unit=food.nutritional_info_unit,
    )

    if food.nutritional_info_size != 1:
        Serving.objects.create(
            food=food,
            size=1,
            unit=food.nutritional_info_unit,
        )

    Serving.objects.create(
        food=food,
        size=1,
        unit=UNIT_CONTAINER,
    )

    if food.num_servings > 1:
        Serving.objects.create(
            food=food,
            size=1,
            unit=UNIT_SERVING,
        )


@receiver(post_save, sender=FoodProduct)
def update_servings_on_nutritional_change(
    sender: FoodProduct,  # pylint: disable=unused-argument
    instance: FoodProduct,
    created: bool,
    **kwargs: Any,
):
    """Update servings on a nutritional change.

    Args:
        sender (FoodProduct): signal sender.
        instance (FoodProduct): instance to be saved.
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    if created:
        return

    food = Food.objects.get(id=instance.id)

    for serving in food.servings.all():
        serving.save()
