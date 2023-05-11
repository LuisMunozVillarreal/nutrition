"""plans app signal handlers module."""


from typing import Any

from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.plans.models import Intake


@receiver(pre_save, sender=Intake)
def increase_day_nutrients(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: dict[Any, Any],
) -> None:
    """Increase day nutrients.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        kwargs (dict[Any, Any]): keyword arguments.
    """
    created = instance.id is None
    food = instance
    day = instance.day

    for nutrient in NUTRIENT_LIST:
        old_food_value = 0
        new_food_value = getattr(food, nutrient)
        if not new_food_value:
            continue

        if not created:
            db_food = Intake.objects.get(id=instance.id)
            old_food_value = getattr(db_food, nutrient)

        diff = new_food_value - old_food_value
        day_value = getattr(day, nutrient) or 0
        setattr(day, nutrient, day_value + diff)

    day.save()


@receiver(pre_delete, sender=Intake)
def decrease_day_nutrients(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: dict[Any, Any],
) -> None:
    """Decrease day nutrients.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        kwargs (dict[Any, Any]): keyword arguments.
    """
    food = instance
    day = instance.day

    for nutrient in NUTRIENT_LIST:
        day_value = getattr(day, nutrient)
        food_value = getattr(food, nutrient)
        if food_value:
            setattr(day, nutrient, day_value - food_value)

    day.save()
