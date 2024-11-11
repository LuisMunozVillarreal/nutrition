"""food app signal handlers for the cupboard."""

from decimal import Decimal
from typing import Any

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from pint import UnitRegistry

from apps.foods.models import (
    CupboardItem,
    CupboardItemServing,
    Food,
    Recipe,
    Serving,
)
from apps.foods.models.units import UNIT_CONTAINER, UNIT_GRAM, UNIT_SERVING
from apps.plans.models import Intake


def _get_consumed_g(ureg: UnitRegistry, serving: Serving) -> Decimal:
    """Get consumed grams.

    Args:
        ureg (UnitRegistry): UnitRegistry instance.
        serving (Serving): serving to get the consumed grams from.

    Returns:
        Decimal: consumed grams.
    """
    unit = serving.unit
    if unit in (UNIT_CONTAINER, UNIT_SERVING):
        unit = serving.weight_unit

    return (
        (ureg.Quantity(Decimal(str(serving.weight))) * ureg(unit))
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
        ureg = serving.UREG

        cupboard_item = CupboardItem.objects.filter(
            food=serving.food, finished=False
        ).first()
        if not cupboard_item:
            continue

        CupboardItemServing.objects.create_from_serving(
            item=cupboard_item, serving=serving
        )

        consumed_g = Decimal("0")
        for cupboard_serving in cupboard_item.servings.all():
            consumed_g += _get_consumed_g(ureg, cupboard_serving)

        cupboard_item.consumed_perc = _get_consumed_perc(
            ureg, cupboard_item.food, consumed_g
        )
        cupboard_item.save()


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
        created (bool): whether is created or not.
        kwargs (Any): keyword arguments.
    """
    if not created:
        return

    serving = CupboardItemServing.objects.filter(pk=instance.food.pk).first()
    if not serving:
        return

    ureg = serving.UREG

    consumed_g = _get_consumed_g(ureg, serving)

    cupboard_item = serving.item
    cupboard_item.consumed_perc = _get_consumed_perc(
        ureg, cupboard_item.food, consumed_g
    )
    cupboard_item.save()


class CupboardItemAlreadyConsumedError(Exception):
    """Cupboard Item Already Consumd Error."""


class CupboardItemServingTooBigError(Exception):
    """Cupboard Item Serving Too Big Error."""


@receiver(pre_save, sender=CupboardItemServing)
def control_finished_items(
    sender: CupboardItemServing,  # pylint: disable=unused-argument
    instance: CupboardItemServing,
    **kwargs: Any,
) -> None:
    """Control finished items.

    Args:
        sender (CupboardItemServing): signal sender.
        instance (CupboardItemServing): instance to be saved.
        kwargs (Any): keyword arguments.

    Raises:
        CupboardItemAlreadyConsumedError: if the cupboard item is already
            consumed.
        CupboardItemServingTooBigError: if the cupboard item serving is too
            big to be consumed.
    """
    if instance.id is not None:
        return

    if instance.item.finished:
        raise CupboardItemAlreadyConsumedError()

    serving = instance
    ureg = serving.UREG

    consumed_g = _get_consumed_g(ureg, serving)

    cupboard_item = serving.item
    consumed_perc = _get_consumed_perc(ureg, cupboard_item.food, consumed_g)

    if cupboard_item.consumed_perc + consumed_perc > 100:
        raise CupboardItemServingTooBigError()
