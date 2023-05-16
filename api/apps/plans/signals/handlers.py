"""plans app signal handlers module."""


import datetime
from typing import Any

from django.db.models.signals import (
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver

from apps.exercises.models import Exercise
from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.plans.models import Day, Intake, WeekPlan


@receiver(post_save, sender=WeekPlan)
def create_week_days(
    sender: WeekPlan,  # pylint: disable=unused-argument
    instance: WeekPlan,
    created: bool,
    **kwargs: Any,
) -> None:
    """Create week days.

    Args:
        sender (WeekPlan): signal sender.
        instance (WeekPlan): instance to be saved.
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    if not created:
        return

    plan = instance

    for num in range(plan.PLAN_LENGTH_DAYS):
        Day.objects.create(
            plan=plan,
            day=plan.start_date + datetime.timedelta(num),
            day_num=num + 1,
            deficit=(plan.deficit * plan.DEFICIT_DISTRIBUTION[num] / 100),
        )


@receiver(pre_save, sender=Intake)
def increase_day_nutrients(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Increase day nutrients.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        kwargs (Any): keyword arguments.
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
    **kwargs: Any,
) -> None:
    """Decrease day nutrients.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be deleted.
        kwargs (Any): keyword arguments.
    """
    food = instance
    day = instance.day

    for nutrient in NUTRIENT_LIST:
        day_value = getattr(day, nutrient)
        food_value = getattr(food, nutrient)
        if food_value:
            setattr(day, nutrient, day_value - food_value)

    day.save()


@receiver(post_save, sender=Exercise)
def increase_day_goals_and_percs(
    sender: Exercise,  # pylint: disable=unused-argument
    instance: Exercise,
    **kwargs: Any,
) -> None:
    """Increase day goals.

    Args:
        sender (Exercise): signal sender.
        instance (Exercise): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    instance.day.save()


@receiver(post_delete, sender=Exercise)
def decrease_day_goals_and_percs(
    sender: Exercise,  # pylint: disable=unused-argument
    instance: Exercise,
    **kwargs: Any,
) -> None:
    """Decrease day nutrients.

    Args:
        sender (Exercise): signal sender.
        instance (Exercise): instance to be deleted.
        kwargs (Any): keyword arguments.
    """
    instance.day.save()
