"""food app signal handlers for the cupboard."""

from decimal import Decimal
from typing import Any

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.foods.models import CupboardItem, CupboardItemServing, Recipe
from apps.foods.models.units import UNIT_GRAM
from apps.plans.models import Intake


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

    recipes = Recipe.objects.filter(pk=instance.food.pk)
    if not recipes.exists():
        return

    recipe = recipes.first()

    for recipe_ingredient in recipe.ingredients.all():  # type: ignore
        serving = recipe_ingredient.food
        ureg = serving.UREG

        qs = CupboardItem.objects.filter(food=serving.food, finished=False)

        cupboard_item = qs.first()
        CupboardItemServing.objects.create_from_serving(
            item=cupboard_item, serving=serving
        )

        consumed_g = 0
        for cupboard_serving in cupboard_item.servings.all():  # type: ignore
            consumed_g += (
                (
                    ureg.Quantity(Decimal(str(cupboard_serving.size)))
                    * ureg(cupboard_serving.unit)
                )
                .to(UNIT_GRAM)
                .m
            )

        cupboard_item_g = (
            ureg.Quantity(
                Decimal(str(cupboard_item.food.weight))  # type: ignore
                * ureg(cupboard_item.food.weight_unit)  # type: ignore
            )
            .to(UNIT_GRAM)
            .m
        )
        cupboard_item.consumed_perc = (  # type: ignore
            consumed_g * 100 / cupboard_item_g
        )
        cupboard_item.save()  # type: ignore


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

    serving = instance.food

    if not CupboardItemServing.objects.filter(pk=serving.pk).exists():
        return

    ureg = serving.UREG

    consumed_g = (
        (ureg.Quantity(Decimal(str(serving.size))) * ureg(serving.unit))
        .to(UNIT_GRAM)
        .m
    )

    cupboard_item = serving.item  # type: ignore
    cupboard_item_g = (
        ureg.Quantity(
            Decimal(str(cupboard_item.food.weight))
            * ureg(cupboard_item.food.weight_unit)
        )
        .to(UNIT_GRAM)
        .m
    )
    cupboard_item.consumed_perc = consumed_g * 100 / cupboard_item_g
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
    consumed_g = (
        (ureg.Quantity(Decimal(str(serving.size))) * ureg(serving.unit))
        .to(UNIT_GRAM)
        .m
    )

    cupboard_item = serving.item
    cupboard_item_g = (
        ureg.Quantity(
            Decimal(str(cupboard_item.food.weight))
            * ureg(cupboard_item.food.weight_unit)
        )
        .to(UNIT_GRAM)
        .m
    )
    consumed_perc = consumed_g * 100 / cupboard_item_g

    if cupboard_item.consumed_perc + consumed_perc > 100:
        raise CupboardItemServingTooBigError()
