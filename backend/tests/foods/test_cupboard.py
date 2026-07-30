"""Cupboard tests."""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import close_old_connections, connection
from django.db.models import Sum

from apps.foods.models import Serving
from apps.foods.models.cupboard import CupboardItem, CupboardItemConsumption
from apps.foods.models.units import (
    UNIT_CONTAINER,
    UNIT_MILLILITRE,
    UNIT_SERVING,
    UNIT_UNIT,
)
from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
    recalculate_consumed_perc,
)


@pytest.fixture
def owned_cupboard_day(cupboard_item, day):
    """Match a legacy cupboard fixture to the consuming day's owner."""
    cupboard_item.owner = day.plan.user
    cupboard_item.save(update_fields=["owner"])
    return day


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


def test_cupboard_item_has_nullable_owner_for_legacy_rows():
    """Cupboard items support ownership without invalidating legacy rows."""
    owner_fields = [
        field
        for field in CupboardItem._meta.get_fields()
        if field.name == "owner"
    ]

    assert len(owner_fields) == 1
    assert owner_fields[0].null is True


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
        recipe=recipe,
        food=fp1.servings.filter(serving_unit=UNIT_CONTAINER).first(),
    )
    recipe_ingredient_factory(
        recipe=recipe,
        food=fp2.servings.filter(serving_unit=UNIT_SERVING).first(),
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


def test_cooked_recipe_consumes_each_ingredient_quantity(
    cupboard_item_factory,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
    user_factory,
):
    """Cooking uses the ingredient's fractional or multiple serving count."""
    owner = user_factory()
    product = food_product_factory(size=400, num_servings=4)
    item = cupboard_item_factory(food=product, owner=owner)
    recipe = recipe_factory()
    recipe_ingredient_factory(
        recipe=recipe,
        food=product.servings.get(serving_size=100, serving_unit="g"),
        num_servings=Decimal("2.5"),
    )

    cupboard_item_factory(food=recipe, owner=owner)

    item.refresh_from_db()
    assert item.consumed_perc == Decimal("62.5")


def test_add_cooked_recipe_uses_only_owners_inventory(
    cupboard_item_factory,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
    user_factory,
):
    """Cooking a recipe cannot consume another user's cupboard item."""
    owner = user_factory()
    other_user = user_factory()
    product = food_product_factory()
    recipe = recipe_factory()
    recipe_ingredient_factory(recipe=recipe, food=product.servings.first())
    other_item = cupboard_item_factory(food=product, owner=other_user)
    owner_item = cupboard_item_factory(food=product, owner=owner)

    cupboard_item_factory(food=recipe, owner=owner)

    other_item.refresh_from_db()
    owner_item.refresh_from_db()
    assert other_item.consumed_perc == 0
    assert owner_item.consumed_perc == Decimal("31.25")
    assert CupboardItemConsumption.objects.get().item == owner_item


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


def test_plan_or_consume_cupboard_item(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Cupboard item can be planned or consumed."""
    # When a cupboard item is consumed partially
    intake = intake_factory(
        day=owned_cupboard_day,
        food=cupboard_item.food.servings.first(),
        num_servings=2,
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


def test_liquid_cupboard_item_accepts_compatible_volume_serving(
    cupboard_item_factory,
    day_factory,
    food_product_factory,
    intake_factory,
    user_factory,
):
    """Liquid stock is consumed by converting between volume units."""
    owner = user_factory()
    product = food_product_factory(
        nutritional_info_size=100,
        nutritional_info_unit=UNIT_MILLILITRE,
        size=1,
        size_unit="l",
        num_servings=4,
    )
    item = cupboard_item_factory(food=product, owner=owner)
    serving = product.servings.get(
        serving_size=100, serving_unit=UNIT_MILLILITRE
    )

    intake_factory(day=day_factory(plan__user=owner), food=serving)

    item.refresh_from_db()
    assert item.consumed_perc == Decimal("10")


def test_counted_cupboard_item_accepts_matching_contextual_unit(
    cupboard_item_factory,
    day_factory,
    food_product_factory,
    intake_factory,
    user_factory,
):
    """Non-physical units are valid when stock and serving contexts match."""
    owner = user_factory()
    product = food_product_factory(
        nutritional_info_size=1,
        nutritional_info_unit=UNIT_UNIT,
        size=8,
        size_unit=UNIT_UNIT,
        num_servings=8,
    )
    item = cupboard_item_factory(food=product, owner=owner)
    serving = product.servings.get(serving_unit=UNIT_UNIT)

    intake_factory(
        day=day_factory(plan__user=owner), food=serving, num_servings=2
    )

    item.refresh_from_db()
    assert item.consumed_perc == Decimal("25")


def test_plan_or_consume_uses_only_day_users_inventory(
    cupboard_item_factory,
    day_factory,
    food_product_factory,
    intake_factory,
    user_factory,
):
    """An intake cannot consume another user's cupboard item."""
    owner = user_factory()
    other_user = user_factory()
    product = food_product_factory()
    serving = product.servings.first()
    other_item = cupboard_item_factory(food=product, owner=other_user)
    owner_item = cupboard_item_factory(food=product, owner=owner)
    day = day_factory(plan__user=owner)

    intake = intake_factory(day=day, food=serving)

    other_item.refresh_from_db()
    owner_item.refresh_from_db()
    assert other_item.consumed_perc == 0
    assert owner_item.consumed_perc == Decimal("31.25")
    assert intake.cupboard_item_consumption.item == owner_item


def test_remove_intake(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Remove intake recalculates cupboard item consumption."""
    # Given an intake that has consumed a cupboard item
    intake = intake_factory(
        day=owned_cupboard_day, food=cupboard_item.food.servings.first()
    )
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 31.25
    assert cupboard_item.started is True

    # When the intake is removed
    intake.delete()

    # Then the cupboard item consumption is recalculated and back to zero
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 0
    assert cupboard_item.started is False


def test_add_another_consumption(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Add another consumption reflects in the consumption percentage."""
    # Given a cupboard item that has been partially consumed
    intake_factory(
        day=owned_cupboard_day, food=cupboard_item.food.servings.first()
    )
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 31.25

    # When another consumption is added
    intake_factory(
        day=owned_cupboard_day, food=cupboard_item.food.servings.first()
    )

    # Then the consumed percentage is updated
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 62.5


def test_modify_intake(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Modify an intake reflects on the cupboard item consumption."""
    # Given a cupboard item that has been partially consumed
    intake = intake_factory(
        day=owned_cupboard_day, food=cupboard_item.food.servings.first()
    )
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 31.25

    # When the intake is modified
    intake.num_servings = 3
    intake.save()

    # Then the consumed percentage is updated
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 93.75


def test_linked_consumption_keeps_serving_snapshot_until_intake_edit(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Catalog edits do not silently change historical cupboard consumption."""
    intake = intake_factory(
        day=owned_cupboard_day, food=serving, num_servings=1
    )
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")

    serving.serving_size = Decimal("200")
    serving.save()
    recalculate_consumed_perc(cupboard_item)
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")

    intake.num_servings = Decimal("1.5")
    intake.save()

    cupboard_item.refresh_from_db()
    consumption = intake.cupboard_item_consumption
    assert consumption.num_servings == Decimal("1.5")
    assert cupboard_item.consumed_perc == Decimal("93.75")


@pytest.mark.django_db
def test_legacy_null_consumption_snapshots_are_lazily_resolved(
    cupboard_item, serving
):
    """Rows written by an old replica remain readable during expansion."""
    consumption = CupboardItemConsumption.objects.create(
        item=cupboard_item,
        serving=serving,
        num_servings=Decimal("2"),
    )
    CupboardItemConsumption.objects.filter(pk=consumption.pk).update(
        num_servings=None,
        consumed_amount=None,
        consumed_unit=None,
    )
    consumption.refresh_from_db()

    recalculate_consumed_perc(cupboard_item)

    cupboard_item.refresh_from_db()
    assert consumption.resolved_num_servings == Decimal("1")
    assert consumption.resolved_consumed_snapshot == (Decimal("100"), "g")
    assert cupboard_item.consumed_perc == Decimal("31.25")


@pytest.mark.django_db
def test_saving_legacy_null_consumption_dual_writes_snapshots(
    cupboard_item, serving
):
    """A new writer reconciles every nullable expansion field on save."""
    consumption = CupboardItemConsumption.objects.create(
        item=cupboard_item,
        serving=serving,
    )
    CupboardItemConsumption.objects.filter(pk=consumption.pk).update(
        num_servings=None,
        consumed_amount=None,
        consumed_unit=None,
    )
    consumption.refresh_from_db()

    consumption.save(update_fields=["item"])

    consumption.refresh_from_db()
    assert consumption.num_servings == Decimal("1")
    assert consumption.consumed_amount == Decimal("100")
    assert consumption.consumed_unit == "g"


@pytest.mark.django_db
def test_legacy_null_manual_baseline_is_lazily_reconciled(
    cupboard_item, serving
):
    """An old-writer update remains authoritative until lazily split."""
    CupboardItemConsumption.objects.create(
        item=cupboard_item,
        serving=serving,
    )
    CupboardItem.objects.filter(pk=cupboard_item.pk).update(
        consumed_perc=Decimal("50"),
        manual_consumed_perc=None,
    )
    cupboard_item.refresh_from_db()

    recalculate_consumed_perc(cupboard_item)

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("18.75")
    assert cupboard_item.consumed_perc == Decimal("50")


@pytest.mark.django_db
def test_legacy_null_manual_baseline_is_split_before_a_new_link(
    cupboard_item, serving
):
    """A new link adds to the authoritative legacy total exactly once."""
    CupboardItemConsumption.objects.create(
        item=cupboard_item,
        serving=serving,
    )
    CupboardItem.objects.filter(pk=cupboard_item.pk).update(
        consumed_perc=Decimal("50"),
        manual_consumed_perc=None,
    )
    cupboard_item.refresh_from_db()

    CupboardItemConsumption.objects.create(
        item=cupboard_item,
        serving=serving,
    )

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("18.75")
    assert cupboard_item.consumed_perc == Decimal("81.25")


@pytest.mark.django_db
def test_saving_legacy_null_manual_baseline_dual_writes_the_split(
    cupboard_item, serving
):
    """A new writer safely turns a nullable old-writer total into a baseline."""
    CupboardItemConsumption.objects.create(
        item=cupboard_item,
        serving=serving,
    )
    CupboardItem.objects.filter(pk=cupboard_item.pk).update(
        consumed_perc=Decimal("50"),
        manual_consumed_perc=None,
    )
    cupboard_item.refresh_from_db()

    cupboard_item.consumed_perc = Decimal("60")
    cupboard_item.save()

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("28.75")
    assert cupboard_item.consumed_perc == Decimal("60")


def test_manual_consumption_is_preserved_when_intake_is_created(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Creating a linked intake adds to, rather than replaces, manual use."""
    cupboard_item.consumed_perc = Decimal("20")
    cupboard_item.save()

    intake_factory(day=owned_cupboard_day, food=serving)

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("20")
    assert cupboard_item.consumed_perc == Decimal("51.25")


def test_model_save_treats_consumed_percentage_as_total_with_linked_use(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """The model's public consumed percentage retains total-value semantics."""
    intake_factory(day=owned_cupboard_day, food=serving)
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")

    cupboard_item.consumed_perc = Decimal("40")
    cupboard_item.save()

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("8.75")
    assert cupboard_item.consumed_perc == Decimal("40")


def test_manual_consumption_is_preserved_when_intake_is_updated(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Changing a linked intake recalculates on top of the durable baseline."""
    cupboard_item.consumed_perc = Decimal("20")
    cupboard_item.save()
    intake = intake_factory(day=owned_cupboard_day, food=serving)

    intake.num_servings = 2
    intake.save()

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("20")
    assert cupboard_item.consumed_perc == Decimal("82.5")


def test_manual_consumption_is_restored_when_intake_is_deleted(
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Deleting the last linked intake restores the manual baseline."""
    cupboard_item.consumed_perc = Decimal("20")
    cupboard_item.save()
    intake = intake_factory(day=owned_cupboard_day, food=serving)

    intake.delete()

    cupboard_item.refresh_from_db()
    assert cupboard_item.manual_consumed_perc == Decimal("20")
    assert cupboard_item.consumed_perc == Decimal("20")


def test_finish_cupboard_item(
    day, intake_factory, cupboard_item_factory, food_product_factory
):
    """Cupboard item gets finished."""
    # Given a product with 3 servings
    product = food_product_factory(num_servings=3)

    # And a serving that is a third of the product
    serving = product.servings.last()

    # And a cupboard item from that product
    cupboard_item = cupboard_item_factory(food=product, owner=day.plan.user)

    # And a cupboard item that is two thirds consumed
    intake_factory(day=day, food=serving, num_servings=2)

    # When the last thrid is consumed
    intake_factory(day=day, food=serving, num_servings=1)

    # Then the item appears as finished
    cupboard_item.refresh_from_db()
    assert cupboard_item.finished is True


def test_try_consume_more_than_left(
    intake_factory, cupboard_item, serving, owned_cupboard_day
):
    """Consuming more than available isn't possible."""
    # Given a cupboard item that is almost consumed
    intake_factory(
        day=owned_cupboard_day, food=serving, num_servings=Decimal("3")
    )

    # When a serving that is bigger than the remaining cupboard product
    # is tried to be consumed
    # Then an error is raised
    with pytest.raises(CupboardItemConsumptionTooBigError):
        intake_factory(day=owned_cupboard_day, food=serving)


def test_linked_consumption_locks_cupboard_item_before_write(
    mocker, cupboard_item, serving
):
    """Every linked write serializes decisions on the cupboard row."""
    lock = mocker.spy(CupboardItem.objects, "select_for_update")

    CupboardItemConsumption.objects.create(item=cupboard_item, serving=serving)

    lock.assert_called_once_with()


def test_linked_consumption_update_locks_cupboard_item_before_write(
    mocker, cupboard_item, serving
):
    """Updating a linked amount is serialized on the cupboard row."""
    consumption = CupboardItemConsumption.objects.create(
        item=cupboard_item, serving=serving
    )
    lock = mocker.spy(CupboardItem.objects, "select_for_update")

    consumption.num_servings = Decimal("2")
    consumption.save()

    lock.assert_called_once_with()


def test_linked_consumption_delete_locks_cupboard_item_before_write(
    mocker, cupboard_item, serving
):
    """Deleting a linked amount is serialized on the cupboard row."""
    consumption = CupboardItemConsumption.objects.create(
        item=cupboard_item, serving=serving
    )
    lock = mocker.spy(CupboardItem.objects, "select_for_update")

    consumption.delete()

    lock.assert_called_once_with()


def test_linked_consumption_rolls_back_when_recalculation_fails(
    mocker, cupboard_item, serving
):
    """The link insert and total recalculation are one atomic operation."""
    mocker.patch(
        "apps.foods.signals.handlers.cupboard.recalculate_consumed_perc",
        side_effect=RuntimeError("injected recalculation failure"),
    )

    with pytest.raises(RuntimeError, match="injected recalculation failure"):
        CupboardItemConsumption.objects.create(
            item=cupboard_item, serving=serving
        )

    assert CupboardItemConsumption.objects.count() == 0


def test_linked_consumption_update_rolls_back_when_recalculation_fails(
    mocker, cupboard_item, serving
):
    """A snapshot update and its total recalculation commit together."""
    consumption = CupboardItemConsumption.objects.create(
        item=cupboard_item, serving=serving
    )
    cupboard_item.refresh_from_db()
    original_total = cupboard_item.consumed_perc
    mocker.patch(
        "apps.foods.signals.handlers.cupboard.recalculate_consumed_perc",
        side_effect=RuntimeError("injected recalculation failure"),
    )

    consumption.num_servings = Decimal("2")
    with pytest.raises(RuntimeError, match="injected recalculation failure"):
        consumption.save()

    consumption.refresh_from_db()
    cupboard_item.refresh_from_db()
    assert consumption.num_servings == Decimal("1")
    assert consumption.consumed_amount == Decimal("100")
    assert cupboard_item.consumed_perc == original_total


def test_linked_consumption_delete_rolls_back_when_recalculation_fails(
    mocker, cupboard_item, serving
):
    """A link deletion and its total recalculation commit together."""
    consumption = CupboardItemConsumption.objects.create(
        item=cupboard_item, serving=serving
    )
    cupboard_item.refresh_from_db()
    original_total = cupboard_item.consumed_perc
    mocker.patch(
        "apps.foods.signals.handlers.cupboard.recalculate_consumed_perc",
        side_effect=RuntimeError("injected recalculation failure"),
    )

    with pytest.raises(RuntimeError, match="injected recalculation failure"):
        consumption.delete()

    assert CupboardItemConsumption.objects.filter(pk=consumption.pk).exists()
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == original_total


@pytest.mark.skipif(
    not connection.features.has_select_for_update,
    reason="Database backend cannot exercise row-lock concurrency",
)
@pytest.mark.django_db(transaction=True)
def test_concurrent_linked_consumptions_cannot_both_overconsume(
    cupboard_item_factory, food_product_factory
):
    """Concurrent decisions serialize so only one 60% link can persist."""
    product = food_product_factory(size=Decimal("100"), num_servings=1)
    item = cupboard_item_factory(food=product)
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("60"), serving_unit="g"
    )
    ready = threading.Barrier(2)

    def consume() -> str:
        close_old_connections()
        try:
            stale_item = CupboardItem.objects.get(pk=item.pk)
            thread_serving = Serving.objects.get(pk=serving.pk)
            ready.wait(timeout=10)
            try:
                CupboardItemConsumption.objects.create(
                    item=stale_item, serving=thread_serving
                )
            except CupboardItemConsumptionTooBigError:
                return "rejected"
            return "created"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(), range(2)))

    item.refresh_from_db()
    assert sorted(results) == ["created", "rejected"]
    assert item.consumptions.count() == 1
    assert item.consumed_perc == Decimal("60")


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
    cupboard_item, serving, intake_factory, owned_cupboard_day
):
    """Existing cupboard item serving can't be consumed twice."""
    # And the serving is part of an intake
    intake_factory(day=owned_cupboard_day, food=serving)

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
    intake_factory, serving, cupboard_item, owned_cupboard_day
):
    """Unprocessed intake that becomes processed consumes the cupboard.

    When an intake is created without a food product, it's considered
    unprocessed. This is done, usually with some notes or a picture, in order
    to create and add the food product later on.

    Once the intake is linked to a food product, it needs to taken into account
    in the cupboard as well.
    """
    # Given an unprocessed intake
    intake = intake_factory(day=owned_cupboard_day, food=None)

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
    intake_factory, serving, cupboard_item, owned_cupboard_day
):
    """Processed intake that becomes unprocessed unconsumes the cupboard."""
    # Given an unprocessed intake
    intake = intake_factory(day=owned_cupboard_day, food=serving)

    # And the cupboard item is not consumed
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == Decimal("31.25")

    # When the intake is processed
    intake.food = None
    intake.save()

    # Then the cupboard consumption should increase
    cupboard_item.refresh_from_db()
    assert cupboard_item.consumed_perc == 0
