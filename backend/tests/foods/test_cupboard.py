"""Cupboard tests."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from apps.foods.models.cupboard import CupboardItem, CupboardItemConsumption
from apps.foods.models.units import UNIT_CONTAINER, UNIT_SERVING
from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
)


def test_add_food_to_cupboard(cupboard_item_factory):
    """Food is added to the cupboard correctly."""
    # When a food product is added to the cupboard
    item = cupboard_item_factory()

    # Then the cupboard contains a zero consumed cupboard item
    assert item.consumed_perc == 0

    # And all its servings are available
    assert item.servings.count() == 0

    # And it's not started
    assert item.started is False

    # And it's not finished
    assert item.finished is False


def test_add_cooked_recipe_to_cupboard(
    cupboard_item_factory,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
):
    """Cooked recipes are added to the cupboard correctly."""
    # Given a few food products in the cupboard
    fp1 = food_product_factory()
    fp2 = food_product_factory()

    cfp1 = cupboard_item_factory(food=fp1)
    cfp2 = cupboard_item_factory(food=fp2)

    # And a recipe made of those products
    recipe = recipe_factory()
    recipe_ingredient_factory(
        recipe=recipe, food=fp1.servings.filter(unit=UNIT_CONTAINER).first()
    )
    recipe_ingredient_factory(
        recipe=recipe, food=fp2.servings.filter(unit=UNIT_SERVING).first()
    )
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())

    # When that recipe is added to the cupboard
    cupboard_item_factory(food=recipe)

    # Then the required food products servings to cook that recipe have been
    # added as consumed to the cupboard
    assert CupboardItemConsumption.objects.count() == 3

    # And the consumed percentage is correct
    cfp1.refresh_from_db()
    assert cfp1.consumed_perc == 100
    cfp2.refresh_from_db()
    assert cfp2.consumed_perc == 81.25


def test_add_cooked_recipe_to_an_empty_cupboard(
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
    cupboard_item_factory,
):
    """Cooked recipe can be added to an empty cupboard."""
    # Given a few food products in the cupboard
    fp1 = food_product_factory()
    fp2 = food_product_factory()

    # And a recipe made of those products
    recipe = recipe_factory()
    recipe_ingredient_factory(recipe=recipe, food=fp1.servings.first())
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())

    # When that recipe is added to the cupboard
    cupboard_item = cupboard_item_factory(food=recipe)

    # Then the recipe is in the cupboard
    assert CupboardItem.objects.count() == 1
    assert CupboardItem.objects.first() == cupboard_item


def test_plan_or_consume_cupboard_item(cupboard_item, serving, intake_factory):
    """Cupboard item can be planned or consumed."""
    # When a cupboard item is consumed partially
    intake_factory(food=cupboard_item.food.servings.first(), num_servings=2)

    # Then the item serving portion appears as consumed in the cupboard
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 62.5

    # And the item appears as started, but not finished
    assert cupboard_item.started is True
    assert cupboard_item.finished is False

    # And there is a consumption based in the serving in the DB
    assert CupboardItemConsumption.objects.count() == 1
    assert CupboardItemConsumption.objects.first().serving == serving
    assert CupboardItemConsumption.objects.first().num_servings == 2


def test_finish_cupboard_item(intake_factory, cupboard_item, serving):
    """Cupboard item gets finished."""
    # When a serving as big as the cupboard item is consumed
    intake_factory(food=serving, num_servings=Decimal("3.2"))

    # Then the item appears as finished
    cupboard_item.refresh_from_db()
    assert cupboard_item.finished is True


def test_try_consume_more_than_left(intake_factory, cupboard_item, serving):
    """Consuming more than available isn't possible."""
    # Given a cupboard item that is almost consumed
    intake_factory(food=serving, num_servings=Decimal("3"))

    # When a serving that is bigger than the remaining cupboard product
    # is tried to be consumed
    # Then an error is raised
    with pytest.raises(CupboardItemConsumptionTooBigError):
        intake_factory(food=serving)


def test_plan_or_consume_non_cupboard_item(day, intake_factory):
    """Non cupboard item can be plan or consumed."""
    # Given an empty cupboard
    assert CupboardItem.objects.count() == 0

    # And no calories consumed
    assert day.calorie_intake_perc == 0

    # When a non cupboard item is linked to an intake
    intake_factory(day=day)

    # Then the consumed calories increase
    assert day.calorie_intake_perc == Decimal("5.416318915146885050465171863")

    # And the cupboard remains the same
    assert CupboardItem.objects.count() == 0


def test_existing_cupboard_item_does_not_consume_other_items_twice(
    cupboard_item_factory,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
):
    """Existing cupboard item does not consume other items twice.

    When a cooked recipe is added as cupboard item, the existing cupboard items
    from food products are consumed. When a cooked recipe cupboard item is
    saved afterwards, the consumption should not be done again.
    """
    # Given a few food products in the cupboard
    fp1 = food_product_factory()
    fp2 = food_product_factory()

    cupboard_item_factory(food=fp1)
    cupboard_item_factory(food=fp2)

    # And a recipe made of those products
    recipe = recipe_factory()
    recipe_ingredient_factory(recipe=recipe, food=fp1.servings.first())
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())

    # And that recipe being added to the cupboard
    item = cupboard_item_factory(food=recipe)

    # And a given current consumption
    consumption = CupboardItem.objects.aggregate(Sum("consumed_perc"))[
        "consumed_perc__sum"
    ]

    assert consumption == Decimal("93.75")

    # When the cupboard item is saved again
    item.save()

    # The consumption remains the same
    assert (
        consumption
        == CupboardItem.objects.aggregate(Sum("consumed_perc"))[
            "consumed_perc__sum"
        ]
    )


def test_existing_cupboard_item_consump_does_not_consume_cupboard_item_twice(
    cupboard_item, serving, intake_factory
):
    """Existing cupboard item serving can't be consumed twice."""
    # And the serving is part of an intake
    intake_factory(food=serving)

    # And a cupboard item consumption
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")

    # When the related cupboard item serving is saved
    cupboard_item.servings.first().save()

    # Then the cupboard item consumption remains the same
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")


def test_cupboard_str_based_on_product(cupboard_item_factory, food_product):
    """Cupboard item string representation is based on the product."""
    # Given a cupboard item based on a food product
    item = cupboard_item_factory(food=food_product)

    # When the item is converted to a string
    res = str(item)

    # Then the string representation is the same as the food product
    assert res == str(food_product)


def test_cupboard_str_based_on_recipe(cupboard_item_factory, recipe):
    """Cupboard item string representation is based on the recipe."""
    # Given a cupboard item based on a recipe
    item = cupboard_item_factory(food=recipe)

    # When the item is converted to a string
    res = str(item)

    # Then the string representation is the same as the recipe
    assert res == str(recipe)
