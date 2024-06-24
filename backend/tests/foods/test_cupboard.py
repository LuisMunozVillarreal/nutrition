import pytest

from apps.foods.signals.handlers.cupboard import CupboardItemAlreadyConsumedError, CupboardItemServingTooBigError


def test_add_food_to_cupboard(cupboard_item_factory):
    # When a food product is added to the cupboard
    item = cupboard_item_factory()

    # Then the cupboard contains a zero consumed cupboard item
    assert item.consumed_perc == 0

    # And all its servings are available
    assert item.servings.count() == 0

    # And it's not started
    assert item.started == False

    # And it's not finished
    assert item.finished == False


def test_add_cooked_recipe_to_cupboard(
    cupboard_item_factory,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
):
    # Given a few food products in the cupboard
    fp1 = food_product_factory()
    fp2 = food_product_factory()

    cfp1 = cupboard_item_factory(food=fp1)
    cfp2 = cupboard_item_factory(food=fp2)

    # And a recipe made of those products
    recipe = recipe_factory()
    recipe_ingredient_factory(recipe=recipe, food=fp1.servings.first())
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())
    recipe_ingredient_factory(recipe=recipe, food=fp2.servings.first())

    # When that recipe is added to the cupboard
    cupboard_item_factory(food=recipe)

    # Then the required food products servings to cook that recipe have been
    # removed from the cupboard
    cfp1.refresh_from_db()
    assert cfp1.consumed_perc == 31.25
    cfp2.refresh_from_db()
    assert cfp2.consumed_perc == 62.5


def test_plan_or_consume_cupboard_item(cupboard_item_serving, intake_factory):
    # When a cupboard item serving is linked to an intake
    intake_factory(food=cupboard_item_serving)

    # Then the item serving portion appears as consumed in the cupboard
    assert cupboard_item_serving.item.consumed_perc == 31.25

    # And the item appears as started, but not finished
    assert cupboard_item_serving.item.started is True
    assert cupboard_item_serving.item.finished is False


def test_finish_cupboard_item(intake_factory, cupboard_item_serving_factory):
    # Given a serving as big as the cupboard item
    serving = cupboard_item_serving_factory(size=320)

    # When that serving is consumed
    intake_factory(food=serving)

    # Then the item appears as finished
    assert serving.item.finished == True


def test_try_plan_finished_item(intake_factory, cupboard_item_serving_factory):
    # Given an already finished item
    serving = cupboard_item_serving_factory(size=320)
    intake_factory(food=serving)
    assert serving.item.finished is True

    # When an already finished item is tried to be consumed
    # Then an error is raised
    with pytest.raises(CupboardItemAlreadyConsumedError):
        intake_factory(food=cupboard_item_serving_factory(item=serving.item))


def test_try_consume_more_than_left(intake_factory, cupboard_item_serving_factory):
    # When a serving that is bigger than the remaining cupboard product
    # is tried to be consumed
    serving = cupboard_item_serving_factory(size=300)
    intake_factory(food=serving)

    # Then an error is raised
    with pytest.raises(CupboardItemServingTooBigError):
        intake_factory(food=cupboard_item_serving_factory(item=serving.item))


# def test_plan_or_consume_non_cupboard_item():
#     # When a non cupboard item is linked to an intake

#     # Then the consumed calories increase

#     # And the cupboard remains the same
