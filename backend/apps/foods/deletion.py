"""Canonical row locking for nutrition-affecting deletion cascades."""

from typing import Any, cast

from django.apps import apps
from django.db import models, router, transaction


class NutritionDeletionQuerySet(models.QuerySet):
    """QuerySet that locks nutrition aggregate owners before collection."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Delete rows after acquiring all affected aggregate-owner locks.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        using = self.db
        with transaction.atomic(using=using):
            lock_nutrition_deletion(self, using)
            return super().delete()


class NutritionDeletionManager(
    models.Manager.from_queryset(NutritionDeletionQuerySet)  # type: ignore[misc]
):
    """Manager exposing nutrition-safe bulk deletion."""


class NutritionDeletionMixin:
    """Acquire aggregate-owner locks before Django builds a delete collector."""

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Delete one row under the same locks used by bulk deletion.

        Args:
            args (Any): Positional arguments forwarded to Django deletion.
            kwargs (Any): Keyword arguments forwarded to Django deletion.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        instance = cast(models.Model, self)
        model = type(instance)
        using = kwargs.get("using") or router.db_for_write(
            model, instance=instance
        )
        manager = cast(Any, model).objects
        targets = manager.using(using).filter(pk=instance.pk)
        with transaction.atomic(using=using):
            lock_nutrition_deletion(targets, using)
            return models.Model.delete(instance, *args, **kwargs)


def lock_nutrition_deletion(targets: models.QuerySet, using: str) -> None:
    """Lock every affected Day, then every CupboardItem, by ascending PK.

    Args:
        targets (models.QuerySet): Rows whose deletion cascade will be collected.
        using (str): Database alias used by the deletion transaction.
    """
    serving_model = apps.get_model("foods", "Serving")
    food_model = apps.get_model("foods", "Food")
    intake_model = apps.get_model("plans", "Intake")
    cupboard_item_model = apps.get_model("foods", "CupboardItem")
    consumption_model = apps.get_model("foods", "CupboardItemConsumption")

    if issubclass(targets.model, serving_model):
        serving_ids = list(targets.values_list("pk", flat=True))
        intake_day_ids = (
            intake_model.objects.using(using)
            .filter(food_id__in=serving_ids)
            .values_list("day_id", flat=True)
            .distinct()
        )
        affected_consumptions = consumption_model.objects.using(using).filter(
            serving_id__in=serving_ids
        )
    elif issubclass(targets.model, food_model):
        food_ids = list(targets.values_list("pk", flat=True))
        serving_ids = list(
            serving_model.objects.using(using)
            .filter(food_id__in=food_ids)
            .values_list("pk", flat=True)
        )
        intake_day_ids = (
            intake_model.objects.using(using)
            .filter(food_id__in=serving_ids)
            .values_list("day_id", flat=True)
            .distinct()
        )
        affected_consumptions = consumption_model.objects.using(using).filter(
            serving_id__in=serving_ids
        )
    elif issubclass(targets.model, consumption_model):
        consumption_ids = list(targets.values_list("pk", flat=True))
        affected_consumptions = consumption_model.objects.using(using).filter(
            pk__in=consumption_ids
        )
        intake_day_ids = (
            affected_consumptions.exclude(intake_id=None)
            .values_list("intake__day_id", flat=True)
            .distinct()
        )
    else:
        return

    day_ids = sorted(set(intake_day_ids))
    cupboard_item_ids = sorted(
        set(affected_consumptions.values_list("item_id", flat=True))
    )
    if day_ids:
        # Keep plan/day aggregate ordering aligned with all intake writers.
        from apps.plans.locks import lock_plan_aggregate_rows

        lock_plan_aggregate_rows(using=using, day_ids=day_ids)
    if cupboard_item_ids:
        list(
            cupboard_item_model.objects.select_for_update(of=("self",))
            .using(using)
            .filter(pk__in=cupboard_item_ids)
            .order_by("pk")
        )
