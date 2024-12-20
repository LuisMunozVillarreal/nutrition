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

from apps.exercises.models import DaySteps, Exercise
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
def change_day_nutrients(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Change day nutrients on save.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    created = instance.id is None
    day = instance.day
    new_intake = instance
    old_intake = None
    if not created:
        old_intake = Intake.objects.get(id=instance.id)

    for nutrient in NUTRIENT_LIST:
        old_intake_value = 0
        if old_intake and old_intake.food:
            old_intake_value = getattr(old_intake, nutrient) or 0
        new_intake_value = 0
        if new_intake.food:
            new_intake_value = getattr(new_intake, nutrient) or 0

        diff = new_intake_value - old_intake_value
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
    intake = instance
    day = instance.day

    if instance.food is None:
        return

    for nutrient in NUTRIENT_LIST:
        day_value = getattr(day, nutrient)
        intake_value = getattr(intake, nutrient)
        if intake_value:
            setattr(day, nutrient, day_value - intake_value)

    day.save()


@receiver(post_save, sender=Intake)
def recalculate_flags_on_save(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Recalculate day flags on save.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    instance.day.save()


@receiver(post_delete, sender=Intake)
def recalculate_flags_on_delete(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Recalculate day flags on delete.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be deleted.
        kwargs (Any): keyword arguments.
    """
    instance.day.save()


@receiver(post_save, sender=Exercise)
def increase_day_goals_and_percs_and_tracked(
    sender: Exercise,  # pylint: disable=unused-argument
    instance: Exercise,
    **kwargs: Any,
) -> None:
    """Increase day goals and make day tracked.

    Args:
        sender (Exercise): signal sender.
        instance (Exercise): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    instance.day.tracked = True
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


@receiver(post_save, sender=DaySteps)
def enable_steps_flag(
    sender: DaySteps,  # pylint: disable=unused-argument
    instance: DaySteps,
    **kwargs: Any,
) -> None:
    """Enable steps flag.

    Args:
        sender (DayStep): signal sender.
        instance (DayStep): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    instance.day.save()


@receiver(post_delete, sender=DaySteps)
def disable_steps_flag(
    sender: DaySteps,  # pylint: disable=unused-argument
    instance: DaySteps,
    **kwargs: Any,
) -> None:
    """Disable steps flag.

    Args:
        sender (DayStep): signal sender.
        instance (DayStep): instance to be deleted.
        kwargs (Any): keyword arguments.
    """
    day = instance.day
    day.steps = None
    day.save()


@receiver(post_save, sender=Day)
def complete_week(
    sender: Day,  # pylint: disable=unused-argument
    instance: Day,
    **kwargs: Any,
) -> None:
    """Complete week.

    Args:
        sender (Day): signal sender.
        instance (Day): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    instance.plan.save()
