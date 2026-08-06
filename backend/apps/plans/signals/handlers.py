"""plans app signal handlers module."""

import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.db.models.signals import (
    post_delete,
    post_save,
    pre_delete,
)
from django.dispatch import receiver

from apps.exercises.models import (
    DaySteps,
    Exercise,
    get_exercise_deletion_locks,
)
from apps.foods.models.nutrients import NUTRIENT_LIST
from apps.plans.locks import lock_plan_aggregate_rows
from apps.plans.models import Day, Intake, WeekPlan
from apps.plans.models.intake import get_intake_deletion_locks


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


def _recalculate_intake_days(instance: Intake, using: str) -> None:
    """Recompute locked day state from transaction-visible intake rows.

    Intake model writes lock all affected days before any model signal runs.
    Bulk/cascaded deletion obtains the same locks in ``pre_delete`` below. This
    function deliberately derives totals from persisted rows instead of cached
    model arithmetic.

    Args:
        instance (Intake): intake whose affected days are recomputed.
        using (str): database alias used by the write.
    """
    day_ids = getattr(instance, "_nutrition_day_ids", (instance.day_id,))
    aggregate_locks = getattr(instance, "_nutrition_locks", None)
    if aggregate_locks is None or not aggregate_locks.covers_days(
        day_ids, using
    ):
        aggregate_locks = lock_plan_aggregate_rows(
            using=using, day_ids=day_ids
        )
        setattr(instance, "_nutrition_locks", aggregate_locks)
    assert aggregate_locks is not None

    days_by_pk = aggregate_locks.days_by_pk
    days = [days_by_pk[day_id] for day_id in sorted(day_ids)]
    aggregate_fields = {
        nutrient: Sum(nutrient, default=Decimal("0"))
        for nutrient in NUTRIENT_LIST
    }
    for day in days:
        totals = (
            Intake.objects.using(using)
            .filter(day_id=day.pk, processed=True)
            .aggregate(**aggregate_fields)
        )
        for nutrient, total in totals.items():
            setattr(day, nutrient, total)
        day.save(using=using)
        if day.pk == instance.day_id:
            caller_day = getattr(instance, "_caller_day", None)
            if caller_day is not None and caller_day.pk == day.pk:
                for field in Day._meta.concrete_fields:
                    setattr(
                        caller_day, field.attname, getattr(day, field.attname)
                    )
            instance.day = day


@receiver(pre_delete, sender=Exercise)
def lock_day_and_exercise_before_delete(
    sender: Exercise,  # pylint: disable=unused-argument
    instance: Exercise,
    **kwargs: Any,
) -> None:
    """Attach locked aggregate rows before exercise delete handling."""
    using = kwargs["using"]
    with transaction.atomic(using=using):
        deletion_locks = get_exercise_deletion_locks()
        if deletion_locks is not None and deletion_locks.covers(
            instance.pk,
            using,
            instance.day_id,
        ):
            aggregate_locks = deletion_locks.aggregate_locks
            if aggregate_locks is not None:
                if instance.day_id in aggregate_locks.days_by_pk:
                    instance.day = aggregate_locks.days_by_pk[instance.day_id]
                return
            return

        aggregate_locks = lock_plan_aggregate_rows(
            using=using,
            day_ids=() if instance.day_id is None else (instance.day_id,),
        )
        if aggregate_locks is not None and instance.day_id is not None:
            if instance.day_id in aggregate_locks.days_by_pk:
                instance.day = aggregate_locks.days_by_pk[instance.day_id]
            setattr(instance, "_plan_aggregate_locks", aggregate_locks)


@receiver(pre_delete, sender=Intake)
def lock_day_and_intake_before_delete(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Lock WeekPlan, then Day, then Intake for bulk/cascade deletion.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be deleted.
        kwargs (Any): keyword arguments.
    """
    using = kwargs["using"]
    with transaction.atomic(using=using):
        aggregate_locks = getattr(instance, "_nutrition_locks", None)
        deletion_locks = get_intake_deletion_locks()
        if (
            aggregate_locks is None
            and deletion_locks is not None
            and deletion_locks.covers(instance.pk, instance.day_id, using)
        ):
            aggregate_locks = deletion_locks.aggregate_locks
            setattr(instance, "_nutrition_locks", aggregate_locks)
        if aggregate_locks is None or not aggregate_locks.covers_days(
            (instance.day_id,), using
        ):
            aggregate_locks = lock_plan_aggregate_rows(
                using=using, day_ids=(instance.day_id,)
            )
            Intake.objects.select_for_update(of=("self",)).using(using).get(
                pk=instance.pk
            )
            setattr(instance, "_nutrition_locks", aggregate_locks)
        assert aggregate_locks is not None
        day = aggregate_locks.days_by_pk[instance.day_id]
        instance.day = day
        setattr(instance, "_nutrition_day_ids", (day.pk,))


@receiver(post_save, sender=Intake)
def recalculate_flags_on_save(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Recalculate nutrition, goals, flags, and plan state on save.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    _recalculate_intake_days(instance, kwargs["using"])


@receiver(post_delete, sender=Intake)
def recalculate_flags_on_delete(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    **kwargs: Any,
) -> None:
    """Recalculate nutrition, goals, flags, and plan state on delete.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be deleted.
        kwargs (Any): keyword arguments.
    """
    _recalculate_intake_days(instance, kwargs["using"])


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
    using = kwargs["using"]
    deletion_locks = get_exercise_deletion_locks()
    if deletion_locks is not None and deletion_locks.covers(
        instance.pk, using, instance.day_id
    ):
        return
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
    """Recalculate week's complete flag.

    Args:
        sender (Day): signal sender.
        instance (Day): instance to be saved.
        kwargs (Any): keyword arguments.
    """
    instance.plan.save()
