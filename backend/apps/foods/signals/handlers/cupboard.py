"""food app signal handlers for the cupboard."""

from decimal import Decimal
from typing import Any

from django.db import router, transaction
from django.db.models.signals import (
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver

from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    Food,
    Recipe,
    Serving,
)
from apps.foods.models.units import (
    UNIT_CONTAINER,
    UNIT_SERVING,
    UNIT_UNIT,
    UREG,
)
from apps.libs.utils import round_no_trailing_zeros
from apps.plans.models import Intake

CONTEXTUAL_UNITS = {UNIT_CONTAINER, UNIT_SERVING, UNIT_UNIT}


def _get_consumed_amount(
    serving: Serving, num_servings: Decimal
) -> tuple[Decimal, str]:
    """Get consumed amount in the serving's concrete stock unit.

    Args:
        serving (Serving): serving to get the consumed grams from.
        num_servings (Decimal): number of servings.

    Returns:
        tuple[Decimal, str]: consumed amount and its concrete unit.
    """
    unit = serving.serving_unit
    if unit in (UNIT_CONTAINER, UNIT_SERVING):
        unit = serving.size_unit

    return Decimal(str(serving.size)) * num_servings, unit


def _get_consumed_perc(
    food: Food, consumed_amount: Decimal, consumed_unit: str
) -> Decimal:
    """Get consumed percentage.

    Args:
        food (Food): food to get the consumed percentage from.
        consumed_amount (Decimal): amount consumed.
        consumed_unit (str): unit for the consumed amount.

    Returns:
        Decimal: consumed percentage.
    """
    stock_unit = food.size_unit
    if consumed_unit in CONTEXTUAL_UNITS or stock_unit in CONTEXTUAL_UNITS:
        if consumed_unit != stock_unit:
            raise ValueError(
                "Consumption unit is incompatible with cupboard stock"
            )
        converted_amount = consumed_amount
    else:
        converted_amount = (
            UREG.Quantity(consumed_amount * UREG(consumed_unit))
            .to(stock_unit)
            .m
        )
    return converted_amount * 100 / Decimal(str(food.size))


def get_linked_consumed_perc(cupboard_item: CupboardItem) -> Decimal:
    """Return the percentage consumed by linked recipes and intakes.

    Args:
        cupboard_item (CupboardItem): cupboard item whose links are totalled.

    Returns:
        Decimal: percentage represented by linked consumptions.
    """
    linked_consumed_perc = Decimal("0")
    for consumption in cupboard_item.consumptions.all():
        linked_consumed_perc += _get_consumed_perc(
            cupboard_item.food,
            *consumption.resolved_consumed_snapshot,
        )

    return linked_consumed_perc


def _reconcile_manual_consumed_perc(
    cupboard_item: CupboardItem,
) -> tuple[Decimal, bool]:
    """Persist a nullable legacy baseline from an authoritative locked row."""
    linked_consumed_perc = get_linked_consumed_perc(cupboard_item)
    if cupboard_item.manual_consumed_perc is not None:
        return linked_consumed_perc, False

    manual_consumed_perc = max(
        cupboard_item.consumed_perc - linked_consumed_perc,
        Decimal("0"),
    )
    CupboardItem.objects.filter(pk=cupboard_item.pk).update(
        manual_consumed_perc=manual_consumed_perc
    )
    cupboard_item.manual_consumed_perc = manual_consumed_perc
    return linked_consumed_perc, True


def recalculate_consumed_perc(
    cupboard_item: CupboardItem, *, already_locked: bool = False
) -> None:
    """Recalculate total consumption from manual and linked portions.

    Args:
        cupboard_item (CupboardItem): cupboard item to recalculate.
        already_locked (bool): whether the caller holds this cupboard row lock.

    Raises:
        CupboardItemConsumptionTooBigError: if total consumption exceeds 100%.
        RuntimeError: if nullable baseline reconciliation does not persist.
    """
    using = router.db_for_write(CupboardItem, instance=cupboard_item)
    with transaction.atomic(using=using):
        authoritative_item = cupboard_item
        if not already_locked:
            authoritative_item = (
                CupboardItem.objects.select_for_update()
                .using(using)
                .select_related("food")
                .get(pk=cupboard_item.pk)
            )
        linked_consumed_perc, reconciled = _reconcile_manual_consumed_perc(
            authoritative_item
        )
        if reconciled:
            # The old writer's stored total is authoritative for this first
            # split. Re-adding its existing links here would double-count them.
            total_consumed_perc = authoritative_item.consumed_perc
        else:
            manual_consumed_perc = authoritative_item.manual_consumed_perc
            if manual_consumed_perc is None:  # pragma: no cover - invariant
                raise RuntimeError("manual baseline reconciliation failed")
            total_consumed_perc = manual_consumed_perc + linked_consumed_perc
        if total_consumed_perc > 100:
            raise CupboardItemConsumptionTooBigError()

        CupboardItem.objects.using(using).filter(
            pk=authoritative_item.pk
        ).update(
            consumed_perc=total_consumed_perc,
            started=total_consumed_perc > 0,
            finished=total_consumed_perc == 100,
        )
        cupboard_item.manual_consumed_perc = (
            authoritative_item.manual_consumed_perc
        )
        cupboard_item.consumed_perc = total_consumed_perc
        cupboard_item.started = total_consumed_perc > 0
        cupboard_item.finished = total_consumed_perc == 100


def _cook_recipe_from_cupboard(
    recipe: Recipe, cooked_item: CupboardItem, using: str
) -> None:
    """Lock recipe stock canonically, then create every ingredient link.

    Nutrition writers acquire ``WeekPlan`` and ``Day`` rows first, an existing
    ``Intake`` row when applicable, and ``CupboardItem`` rows last. A recipe
    fan-out has no plan or intake rows, so it joins that global order at the
    cupboard step and acquires every affected row by ascending primary key.

    Args:
        recipe (Recipe): recipe whose ingredient stock will be consumed.
        cooked_item (CupboardItem): newly created recipe cupboard item.
        using (str): database alias used by the cupboard write.
    """
    ingredients = tuple(
        recipe.ingredients.using(using)
        .select_related("food__food")
        .order_by("pk")
    )
    ingredient_food_ids = {
        ingredient.food.food_id for ingredient in ingredients
    }
    locked_items_by_food: dict[int, CupboardItem] = {}
    for item in (
        CupboardItem.objects.select_for_update(of=("self",))
        .using(using)
        .select_related("food")
        .filter(
            food_id__in=ingredient_food_ids,
            finished=False,
            owner_id=cooked_item.owner_id,
        )
        .order_by("pk")
    ):
        locked_items_by_food.setdefault(item.food_id, item)

    for ingredient in ingredients:
        cupboard_item = locked_items_by_food.get(ingredient.food.food_id)
        if cupboard_item is None:
            continue
        consumption = CupboardItemConsumption(
            item=cupboard_item,
            serving=ingredient.food,
            num_servings=ingredient.num_servings,
        )
        setattr(consumption, "_locked_cupboard_item", (using, cupboard_item))
        try:
            consumption.save(using=using)
        finally:
            delattr(consumption, "_locked_cupboard_item")


@receiver(post_save, sender=CupboardItem)
def calculate_consumption_from_cooked_recipes(
    sender: CupboardItem,  # pylint: disable=unused-argument
    instance: CupboardItem,
    created: bool,
    **kwargs: Any,
) -> None:
    """Calculate consumption from cooked recipes.

    Args:
        sender (CupboardItem): signal sender.
        instance (CupboardItem): instance to be saved.
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    if not created:
        return

    using = kwargs["using"]
    recipe = Recipe.objects.using(using).filter(pk=instance.food.pk).first()
    if not recipe:
        return

    _cook_recipe_from_cupboard(recipe, instance, using)


@receiver(post_save, sender=Intake)
def calculate_consumption_from_intakes(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    created: bool,
    **kwargs: Any,
) -> None:
    """Calculate consumption from intakes.

    Args:
        sender (Intake): signal sender.
        instance (Intake): instance to be saved.
        created (bool): whether the instance is created or not.
        kwargs (Any): keyword arguments.
    """
    # New without food -> no action
    if created and instance.food is None:
        return

    # New with food -> create consumption if there is cupboard item for it
    if created and instance.food is not None:
        item = CupboardItem.objects.filter(
            food=instance.food.food,
            finished=False,
            owner=instance.day.plan.user,
        ).first()
        if not item:
            return

        CupboardItemConsumption.objects.create(
            item=item,
            serving=instance.food,
            num_servings=instance.num_servings,
            intake=instance,
        )
        return

    # Existing without food
    # -> if it had consumption, remove it,
    # -> no action otherwise
    if not created and instance.food is None:
        if hasattr(instance, "cupboard_item_consumption"):
            instance.cupboard_item_consumption.delete()
        return

    # Exixting with food
    # -> if it had consumption, and its food is different from the new one
    # -> if it didn't have food, add consumption,
    if hasattr(instance, "cupboard_item_consumption"):
        instance.cupboard_item_consumption.delete()

    item = CupboardItem.objects.filter(
        food=instance.food.food,  # type: ignore
        finished=False,
        owner=instance.day.plan.user,
    ).first()
    if not item:
        return

    CupboardItemConsumption.objects.create(  # type: ignore
        item=item,
        serving=instance.food,
        num_servings=instance.num_servings,
        intake=instance,
    )


@receiver(post_save, sender=CupboardItemConsumption)
def recalculate_consumption_after_creation(
    sender: CupboardItemConsumption,  # pylint: disable=unused-argument
    instance: CupboardItemConsumption,
    created: bool,  # pylint: disable=unused-argument
    **kwargs: Any,
) -> None:
    """Recalculate consumption after a CupboardItemConsumption gets removed.

    Args:
        sender (CupboardItemConsumption): signal sender.
        instance (CupboardItemConsumption): instance that will be deleted.
        created (bool): whether the instance is created or not.
        kwargs (Any): keyword arguments.
    """
    recalculate_consumed_perc(instance.item, already_locked=True)


@receiver(post_delete, sender=CupboardItemConsumption)
def recalculate_consumption_after_deletion(
    sender: CupboardItemConsumption,  # pylint: disable=unused-argument
    instance: CupboardItemConsumption,
    **kwargs: Any,
) -> None:
    """Recalculate consumption after a CupboardItemConsumption gets removed.

    Args:
        sender (CupboardItemConsumption): signal sender.
        instance (CupboardItemConsumption): instance that will be deleted.
        kwargs (Any): keyword arguments.
    """
    recalculate_consumed_perc(instance.item, already_locked=True)


class CupboardItemConsumptionTooBigError(Exception):
    """Cupboard Item Serving Too Big Error."""


def _lock_cupboard_item(
    instance: CupboardItemConsumption, using: str
) -> CupboardItem:
    """Lock and return the authoritative cupboard row for a linked write."""
    cupboard_item = (
        CupboardItem.objects.select_for_update()
        .using(using)
        .select_related("food")
        .get(pk=instance.item_id)
    )
    instance.item = cupboard_item
    return cupboard_item


@receiver(pre_delete, sender=CupboardItemConsumption)
def lock_cupboard_item_before_deletion(
    sender: CupboardItemConsumption,  # pylint: disable=unused-argument
    instance: CupboardItemConsumption,
    using: str,
    **kwargs: Any,
) -> None:
    """Serialize link deletion and its post-delete total recalculation.

    Args:
        sender (CupboardItemConsumption): signal sender.
        instance (CupboardItemConsumption): instance that will be deleted.
        using (str): database alias used by the deletion.
        kwargs (Any): keyword arguments.
    """
    cupboard_item = _lock_cupboard_item(instance, using)
    _reconcile_manual_consumed_perc(cupboard_item)


@receiver(pre_save, sender=CupboardItemConsumption)
def control_finished_items(
    sender: CupboardItemConsumption,  # pylint: disable=unused-argument
    instance: CupboardItemConsumption,
    using: str,
    **kwargs: Any,
) -> None:
    """Control finished items.

    Args:
        sender (CupboardItemConsumption): signal sender.
        instance (CupboardItemConsumption): instance to be saved.
        using (str): database alias used by the save.
        kwargs (Any): keyword arguments.

    Raises:
        CupboardItemConsumptionTooBigError: if the cupboard item serving is too
            big to be consumed.
        RuntimeError: if an internal prelocked cupboard context is invalid.
    """
    locked_context = getattr(instance, "_locked_cupboard_item", None)
    if locked_context is None:
        cupboard_item = _lock_cupboard_item(instance, using)
    else:
        locked_using, cupboard_item = locked_context
        if locked_using != using or cupboard_item.pk != instance.item_id:
            raise RuntimeError("invalid prelocked cupboard item")
        instance.item = cupboard_item
    _reconcile_manual_consumed_perc(cupboard_item)
    if instance.id is not None:
        return

    consumed_perc = _get_consumed_perc(
        cupboard_item.food,
        *instance.resolved_consumed_snapshot,
    )

    if (
        cupboard_item.consumed_perc + round_no_trailing_zeros(consumed_perc)
        > 100
    ):
        raise CupboardItemConsumptionTooBigError()
