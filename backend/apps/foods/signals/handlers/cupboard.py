"""food app signal handlers for the cupboard."""

from decimal import Decimal
from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from pint import UnitRegistry

from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    Food,
    Recipe,
    Serving,
)
from apps.foods.models.units import UNIT_CONTAINER, UNIT_GRAM, UNIT_SERVING
from apps.libs.utils import round_no_trailing_zeros
from apps.plans.models import Intake


def _get_consumed_g(
    ureg: UnitRegistry, serving: Serving, num_servings: Decimal
) -> Decimal:
    """Get consumed grams.

    Args:
        ureg (UnitRegistry): UnitRegistry instance.
        serving (Serving): serving to get the consumed grams from.
        num_servings (Decimal): number of servings.

    Returns:
        Decimal: consumed grams.
    """
    unit = serving.unit
    if unit in (UNIT_CONTAINER, UNIT_SERVING):
        unit = serving.weight_unit

    return (
        (
            ureg.Quantity(Decimal(str(serving.weight)))
            * num_servings
            * ureg(unit)
        )
        .to(UNIT_GRAM)
        .m
    )


def _get_consumed_perc(
    ureg: UnitRegistry, food: Food, consumed_g: Decimal
) -> Decimal:
    """Get consumed percentage.

    Args:
        ureg (UnitRegistry): UnitRegistry instance.
        food (Food): food to get the consumed percentage from.
        consumed_g (Decimal): consumed grams.

    Returns:
        Decimal: consumed percentage.
    """
    item_g = (
        ureg.Quantity(Decimal(str(food.weight)) * ureg(food.weight_unit))
        .to(UNIT_GRAM)
        .m
    )
    return consumed_g * 100 / item_g


def _set_total_consumed_perc(cupboard_item: CupboardItem) -> None:
    """Set total consumed percentage.

    Args:
        cupboard_item (CupboardItem): cupboard item to set the total consumed
            percentage.
    """
    consumed_g = Decimal("0")
    for consumption in cupboard_item.consumptions.all():
        ureg = consumption.serving.UREG

        num_servings = Decimal("1")
        if consumption.intake:
            num_servings = consumption.intake.num_servings

        consumed_g += _get_consumed_g(ureg, consumption.serving, num_servings)

    if consumed_g:
        cupboard_item.consumed_perc = _get_consumed_perc(
            ureg, cupboard_item.food, consumed_g
        )
    else:
        cupboard_item.consumed_perc = 0

    cupboard_item.save()


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

    recipe = Recipe.objects.filter(pk=instance.food.pk).first()
    if not recipe:
        return

    for recipe_ingredient in recipe.ingredients.all():
        serving = recipe_ingredient.food

        cupboard_item = CupboardItem.objects.filter(
            food=serving.food, finished=False
        ).first()
        if not cupboard_item:
            continue

        CupboardItemConsumption.objects.create(
            item=cupboard_item, serving=serving
        )

        _set_total_consumed_perc(cupboard_item)


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
            food=instance.food.food, finished=False
        ).first()
        if not item:
            return

        CupboardItemConsumption.objects.create(
            item=item,
            serving=instance.food,
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
        food=instance.food.food, finished=False  # type: ignore
    ).first()
    if not item:
        return

    CupboardItemConsumption.objects.create(  # type: ignore
        item=item,
        serving=instance.food,
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
    _set_total_consumed_perc(instance.item)


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
    _set_total_consumed_perc(instance.item)


class CupboardItemConsumptionTooBigError(Exception):
    """Cupboard Item Serving Too Big Error."""


@receiver(pre_save, sender=CupboardItemConsumption)
def control_finished_items(
    sender: CupboardItemConsumption,  # pylint: disable=unused-argument
    instance: CupboardItemConsumption,
    **kwargs: Any,
) -> None:
    """Control finished items.

    Args:
        sender (CupboardItemConsumption): signal sender.
        instance (CupboardItemConsumption): instance to be saved.
        kwargs (Any): keyword arguments.

    Raises:
        CupboardItemConsumptionTooBigError: if the cupboard item serving is too
            big to be consumed.
    """
    if instance.id is not None:
        return

    serving = instance.serving
    ureg = serving.UREG
    num_servings = 1
    if instance.intake:
        num_servings = instance.intake.num_servings

    consumed_g = _get_consumed_g(ureg, serving, num_servings)

    cupboard_item = instance.item
    consumed_perc = _get_consumed_perc(ureg, cupboard_item.food, consumed_g)

    if (
        cupboard_item.consumed_perc + round_no_trailing_zeros(consumed_perc)
        > 100
    ):
        raise CupboardItemConsumptionTooBigError()
