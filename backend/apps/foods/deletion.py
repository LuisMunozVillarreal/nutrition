"""Canonical row locking for nutrition-affecting deletion cascades."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, cast

from django.apps import apps
from django.db import models, router, transaction


@dataclass(frozen=True)
class NutritionDeletionLocks:
    """Every aggregate lock bundle held before Django collects a deletion."""

    recipe_locks: Any | None
    intake_locks: Any | None

    def clear_markers(self) -> None:
        """Remove transaction-scoped markers from prelocked model instances."""
        if self.intake_locks is not None:
            self.intake_locks.aggregate_locks.clear_markers()


@contextmanager
def activate_nutrition_deletion_locks(
    locks: NutritionDeletionLocks,
) -> Iterator[None]:
    """Expose every pre-collector bundle to its deletion signal handlers.

    Args:
        locks (NutritionDeletionLocks): Bundles held by the outer transaction.
    """
    from apps.foods.recipe_locks import activate_recipe_aggregate_locks
    from apps.plans.models.intake import activate_intake_deletion_locks

    with ExitStack() as stack:
        if locks.recipe_locks is not None:
            stack.enter_context(
                activate_recipe_aggregate_locks(locks.recipe_locks)
            )
        if locks.intake_locks is not None:
            stack.enter_context(
                activate_intake_deletion_locks(locks.intake_locks)
            )
        yield


class NutritionDeletionQuerySet(models.QuerySet):
    """QuerySet that locks nutrition aggregate owners before collection."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Delete rows after acquiring all affected aggregate-owner locks.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        using = self.db
        with transaction.atomic(using=using):
            locks = lock_nutrition_deletion(self, using)
            try:
                with activate_nutrition_deletion_locks(locks):
                    return super().delete()
            finally:
                locks.clear_markers()


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
            locks = lock_nutrition_deletion(targets, using)
            try:
                with activate_nutrition_deletion_locks(locks):
                    return models.Model.delete(instance, *args, **kwargs)
            finally:
                locks.clear_markers()


def lock_nutrition_deletion(
    targets: models.QuerySet, using: str
) -> NutritionDeletionLocks:
    """Lock recipes, plans, days, intakes, then cupboard rows by PK.

    Args:
        targets (models.QuerySet): Rows whose deletion cascade will be collected.
        using (str): Database alias used by the deletion transaction.

    Returns:
        NutritionDeletionLocks: Bundles exposed to cascaded deletion signals.
    """
    serving_model = apps.get_model("foods", "Serving")
    food_model = apps.get_model("foods", "Food")
    intake_model = apps.get_model("plans", "Intake")
    cupboard_item_model = apps.get_model("foods", "CupboardItem")
    consumption_model = apps.get_model("foods", "CupboardItemConsumption")
    serving_ids: list[int] = []
    target_recipe_ids: list[int] = []

    if issubclass(targets.model, serving_model):
        serving_ids = list(targets.values_list("pk", flat=True))
        affected_intakes = intake_model.objects.using(using).filter(
            food_id__in=serving_ids
        )
        intake_day_ids = affected_intakes.values_list(
            "day_id", flat=True
        ).distinct()
        affected_consumptions = consumption_model.objects.using(using).filter(
            serving_id__in=serving_ids
        )
    elif issubclass(targets.model, food_model):
        food_ids = list(targets.values_list("pk", flat=True))
        target_recipe_ids = list(
            apps.get_model("foods", "Recipe")
            .objects.using(using)
            .filter(pk__in=food_ids)
            .values_list("pk", flat=True)
        )
        serving_ids = list(
            serving_model.objects.using(using)
            .filter(food_id__in=food_ids)
            .values_list("pk", flat=True)
        )
        affected_intakes = intake_model.objects.using(using).filter(
            food_id__in=serving_ids
        )
        intake_day_ids = affected_intakes.values_list(
            "day_id", flat=True
        ).distinct()
        affected_consumptions = consumption_model.objects.using(using).filter(
            serving_id__in=serving_ids
        )
    elif issubclass(targets.model, consumption_model):
        consumption_ids = list(targets.values_list("pk", flat=True))
        affected_consumptions = consumption_model.objects.using(using).filter(
            pk__in=consumption_ids
        )
        affected_intakes = None
        intake_day_ids = (
            affected_consumptions.exclude(intake_id=None)
            .values_list("intake__day_id", flat=True)
            .distinct()
        )
    else:
        return NutritionDeletionLocks(None, None)

    recipe_locks = None
    if serving_ids:
        recipe_ingredient_model = apps.get_model("foods", "RecipeIngredient")
        recipe_ids = set(target_recipe_ids)
        recipe_ids.update(
            recipe_ingredient_model.objects.using(using)
            .filter(food_id__in=serving_ids)
            .values_list("recipe_id", flat=True)
        )
        if recipe_ids:
            from apps.foods.recipe_locks import lock_recipe_aggregate_rows

            recipe_locks = lock_recipe_aggregate_rows(recipe_ids, using)

    day_ids = sorted(set(intake_day_ids))
    cupboard_item_ids = sorted(
        set(affected_consumptions.values_list("item_id", flat=True))
    )
    intake_locks = None
    if day_ids:
        # Keep plan/day/intake ordering aligned with all intake writers.
        if affected_intakes is not None:
            from apps.plans.models.intake import lock_intake_deletion_rows

            intake_locks = lock_intake_deletion_rows(affected_intakes, using)
        else:
            from apps.plans.locks import lock_plan_aggregate_rows

            lock_plan_aggregate_rows(using=using, day_ids=day_ids)
    if cupboard_item_ids:
        list(
            cupboard_item_model.objects.select_for_update(of=("self",))
            .using(using)
            .filter(pk__in=cupboard_item_ids)
            .order_by("pk")
        )
    return NutritionDeletionLocks(recipe_locks, intake_locks)
