from decimal import Decimal
from typing import Any

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.foods.models import CupboardItem, CupboardItemServing, Recipe
from apps.foods.models.units import UNIT_GRAM
from apps.plans.models import Intake


from apps.foods.models.cupboard import CupboardItem


class CupboardItemNotAvailableError(Exception):
    pass


@receiver(post_save, sender=CupboardItem)
def calculate_consumption_from_cooked_recipes(
    sender: CupboardItem,  # pylint: disable=unused-argument
    instance: CupboardItem,
    created: bool,
    **kwargs: Any,
) -> None:
    if not created:
        return

    if not Recipe.objects.filter(pk=instance.food.pk).exists():
        return

    recipe = Recipe.objects.filter(pk=instance.food.pk).first()

    for recipe_ingredient in recipe.ingredients.all():
        serving = recipe_ingredient.food
        ureg = serving.UREG

        qs = CupboardItem.objects.filter(food=serving.food, finished=False)
        if not qs.exists():
            raise CupboardItemNotAvailableError()

        cupboard_item = qs.first()
        CupboardItemServing.objects.create_from_serving(
            item=cupboard_item, serving=serving
        )

        consumed_g = 0
        for cupboard_serving in cupboard_item.servings.all():
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
                Decimal(str(cupboard_item.food.weight))
                * ureg(cupboard_item.food.weight_unit)
            )
            .to(UNIT_GRAM)
            .m
        )
        cupboard_item.consumed_perc = consumed_g * 100 / cupboard_item_g
        cupboard_item.save()


@receiver(post_save, sender=Intake)
def calculate_consumption_from_intakes(
    sender: Intake,  # pylint: disable=unused-argument
    instance: Intake,
    created: bool,
    **kwargs: Any,
) -> None:
    if not created:
        return

    if not created:
        return

    serving = instance.food

    if not CupboardItemServing.objects.filter(pk=serving.pk).exists():
        return

    ureg = serving.UREG

    consumed_g = (
        (
            ureg.Quantity(Decimal(str(serving.size)))
            * ureg(serving.unit)
        )
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
    cupboard_item.consumed_perc = consumed_g * 100 / cupboard_item_g
    cupboard_item.save()


class CupboardItemAlreadyConsumedError(Exception):
    pass


class CupboardItemServingTooBigError(Exception):
    pass


@receiver(pre_save, sender=CupboardItemServing)
def control_finished_items(
    sender: CupboardItemServing,
    instance: CupboardItemServing,
    **kwargs: Any,
) -> None:
    if instance.id is not None:
        return

    if instance.item.finished:
        raise CupboardItemAlreadyConsumedError()

    serving = instance
    ureg = serving.UREG
    consumed_g = (
        (
            ureg.Quantity(Decimal(str(serving.size)))
            * ureg(serving.unit)
        )
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

