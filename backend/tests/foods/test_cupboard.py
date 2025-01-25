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
    assert item.consumptions.count() == 0

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
    # Given a few food products
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
    intake = intake_factory(
        food=cupboard_item.food.servings.first(), num_servings=2
    )

    # Then the item serving portion appears as consumed in the cupboard
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 62.5

    # And the item appears as started, but not finished
    assert cupboard_item.started is True
    assert cupboard_item.finished is False

    # And there is a consumption based in the serving in the DB
    assert CupboardItemConsumption.objects.count() == 1
    assert CupboardItemConsumption.objects.first().serving == serving
    assert CupboardItemConsumption.objects.first().intake == intake


def test_remove_intake(cupboard_item, serving, intake_factory):
    """Remove intake recalculates cupboard item consumption."""
    # Given an intake that has consumed a cupboard item
    intake = intake_factory(food=cupboard_item.food.servings.first())
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 31.25
    assert cupboard_item.started is True

    # When the intake is removed
    intake.delete()

    # Then the cupboard item consumption is recalculated and back to zero
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 0
    assert cupboard_item.started is False


def test_add_another_consumption(cupboard_item, serving, intake_factory):
    """Add another consumption reflects in the consumption percentage."""
    # Given a cupboard item that has been partially consumed
    intake_factory(food=cupboard_item.food.servings.first())
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 31.25

    # When another consumption is added
    intake_factory(food=cupboard_item.food.servings.first())

    # Then the consumed percentage is updated
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 62.5


def test_modify_intake(cupboard_item, serving, intake_factory):
    """Modify an intake reflects on the cupboard item consumption."""
    # Given a cupboard item that has been partially consumed
    intake = intake_factory(food=cupboard_item.food.servings.first())
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 31.25

    # When the intake is modified
    intake.num_servings = 3
    intake.save()

    # Then the consumed percentage is updated
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 93.75


def test_finish_cupboard_item(
    intake_factory, cupboard_item_factory, food_product_factory
):
    """Cupboard item gets finished."""
    # Given a product with 3 servings
    product = food_product_factory(num_servings=3)

    # And a serving that is a third of the product
    serving = product.servings.last()

    # And a cupboard item from that product
    cupboard_item = cupboard_item_factory(food=product)

    # And a cupboard item that is two thirds consumed
    intake_factory(food=serving, num_servings=2)

    # When the last thrid is consumed
    intake_factory(food=serving, num_servings=1)

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

    # And no energy consumed
    assert day.energy_kcal_intake_perc == 0

    # When a non cupboard item is linked to an intake
    intake_factory(day=day)

    # Then the consumed energy increase
    assert day.energy_kcal_intake_perc == Decimal(
        "5.989596635700075355906352544"
    )

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
    cupboard_item.consumptions.first().save()

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


def test_unprocessed_intake_that_becomes_processed(
    intake_factory, serving, cupboard_item
):
    """Unprocessed intake that becomes processed consumes the cupboard.

    When an intake is created without a food product, it's considered
    unprocessed. This is done, usually with some notes or a picture, in order
    to create and add the food product later on.

    Once the intake is linked to a food product, it needs to taken into account
    in the cupboard as well.
    """
    # Given an unprocessed intake
    intake = intake_factory(food=None)

    # And the cupboard item is not consumed
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 0

    # When the intake is processed
    intake.food = serving
    intake.save()

    # Then the cupboard consumption should increase
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")


def test_processed_intake_that_becomes_unprocessed(
    intake_factory, serving, cupboard_item
):
    """Processed intake that becomes unprocessed unconsumes the cupboard."""
    # Given an unprocessed intake
    intake = intake_factory(food=serving)

    # And the cupboard item is not consumed
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")

    # When the intake is processed
    intake.food = None
    intake.save()

    # Then the cupboard consumption should increase
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 0
