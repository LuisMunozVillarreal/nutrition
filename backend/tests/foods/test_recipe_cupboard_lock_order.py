"""Deterministic lock ordering for cooked-recipe cupboard fan-out."""

# QuerySet internals are intentionally instrumented to verify SQL lock order.
# pylint: disable=protected-access,too-many-arguments,too-many-locals
# pylint: disable=too-many-positional-arguments

from decimal import Decimal

from django.db.models.query import QuerySet

from apps.foods.models import CupboardItem, CupboardItemConsumption, Serving


def test_recipe_fanout_locks_deduplicated_items_by_pk_before_links(
    mocker,
    cupboard_item_factory,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
    user_factory,
):
    """Opposite ingredient order cannot dictate shared cupboard lock order."""
    owner = user_factory()
    first_product = food_product_factory(
        size=Decimal("100"), size_unit="g", num_servings=10
    )
    second_product = food_product_factory(
        size=Decimal("100"), size_unit="g", num_servings=10
    )
    first_serving = Serving.objects.create(
        food=first_product,
        serving_size=Decimal("10"),
        serving_unit="g",
    )
    second_serving = Serving.objects.create(
        food=second_product,
        serving_size=Decimal("10"),
        serving_unit="g",
    )
    first_item = cupboard_item_factory(
        owner=owner,
        food=first_product,
        consumed_perc=Decimal("5"),
    )
    second_item = cupboard_item_factory(
        owner=owner,
        food=second_product,
        consumed_perc=Decimal("7"),
    )
    recipe = recipe_factory()
    recipe_ingredient_factory(recipe=recipe, food=second_serving)
    recipe_ingredient_factory(recipe=recipe, food=first_serving)
    recipe_ingredient_factory(recipe=recipe, food=second_serving)
    events = []
    original_fetch_all = QuerySet._fetch_all
    original_save = CupboardItemConsumption.save

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if (
            was_unfetched
            and queryset.model is CupboardItem
            and queryset.query.select_for_update
        ):
            events.append(
                ("locked", [row.pk for row in queryset._result_cache])
            )

    def record_consumption_save(consumption, *args, **kwargs):
        if consumption._state.adding:
            events.append(("created", consumption.item_id))
        return original_save(consumption, *args, **kwargs)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)
    mocker.patch.object(
        CupboardItemConsumption, "save", new=record_consumption_save
    )

    cupboard_item_factory(owner=owner, food=recipe)

    locked_events = [event for event in events if event[0] == "locked"]
    assert events[0] == ("locked", [first_item.pk, second_item.pk])
    assert locked_events == [
        ("locked", [first_item.pk, second_item.pk]),
    ]
    assert [event[1] for event in events if event[0] == "created"] == [
        second_item.pk,
        first_item.pk,
        second_item.pk,
    ]
    first_item.refresh_from_db()
    second_item.refresh_from_db()
    assert first_item.manual_consumed_perc == Decimal("5")
    assert first_item.consumed_perc == Decimal("15")
    assert second_item.manual_consumed_perc == Decimal("7")
    assert second_item.consumed_perc == Decimal("27")
