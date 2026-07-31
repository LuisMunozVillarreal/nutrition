"""Deterministic aggregate lock ordering for nutrition deletion cascades."""

# QuerySet internals are intentionally instrumented to verify SQL lock order.
# pylint: disable=protected-access,too-many-arguments,too-many-positional-arguments

from decimal import Decimal

import pytest
from django.db.models.query import QuerySet

from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    Food,
    FoodProduct,
)
from apps.plans.models import Day, WeekPlan


def test_serving_delete_locks_day_before_cupboard(
    mocker,
    day_factory,
    food_product_factory,
    serving_factory,
    cupboard_item_factory,
    intake_factory,
):
    """A serving cascade acquires its day lock before its cupboard lock."""
    day = day_factory()
    product = food_product_factory(size=100)
    serving = serving_factory(
        food=product,
        serving_size=10,
        serving_unit="g",
    )
    cupboard_item_factory(
        owner=day.plan.user,
        food=product,
    )
    intake_factory(day=day, food=serving)
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    serving.delete()

    assert locked_models.index(Day) < locked_models.index(CupboardItem)


@pytest.mark.parametrize(
    "delete_as", ["product", "product_queryset", "food_queryset"]
)
def test_product_and_food_delete_lock_day_before_cupboard(
    mocker,
    day_factory,
    food_product_factory,
    serving_factory,
    cupboard_item_factory,
    intake_factory,
    delete_as,
):
    """Every product/food entry point locks cascade owners canonically."""
    day = day_factory()
    product = food_product_factory(size=100)
    serving = serving_factory(food=product, serving_size=10, serving_unit="g")
    cupboard_item_factory(owner=day.plan.user, food=product)
    intake_factory(day=day, food=serving)
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    if delete_as == "product":
        product.delete()
    elif delete_as == "product_queryset":
        FoodProduct.objects.filter(pk=product.pk).delete()
    else:
        Food.objects.filter(pk=product.pk).delete()

    assert locked_models.index(Day) < locked_models.index(CupboardItem)


def test_direct_consumption_delete_locks_day_before_cupboard(
    mocker,
    day_factory,
    food_product_factory,
    serving_factory,
    cupboard_item_factory,
    intake_factory,
):
    """Deleting a link directly follows the same aggregate lock order."""
    day = day_factory()
    product = food_product_factory(size=100)
    serving = serving_factory(food=product, serving_size=10, serving_unit="g")
    cupboard_item_factory(owner=day.plan.user, food=product)
    intake = intake_factory(day=day, food=serving)
    consumption = intake.cupboard_item_consumption
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    consumption.delete()

    assert locked_models.index(Day) < locked_models.index(CupboardItem)


def test_bulk_serving_delete_locks_all_rows_in_stable_pk_order(
    mocker,
    day_factory,
    food_product_factory,
    serving_factory,
    cupboard_item_factory,
    intake_factory,
):
    """A reversed bulk selection still locks all days, then items, by PK."""
    product = food_product_factory(size=100)
    days = [day_factory(), day_factory()]
    servings = [
        serving_factory(food=product, serving_size=10, serving_unit="g")
        for _ in days
    ]
    items = [
        cupboard_item_factory(owner=day.plan.user, food=product)
        for day in days
    ]
    for day, serving in zip(days, servings, strict=True):
        intake_factory(day=day, food=serving)
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    type(servings[0]).objects.filter(
        pk__in=[row.pk for row in servings]
    ).order_by("-pk").delete()

    assert locked_rows[:3] == [
        (WeekPlan, sorted(row.plan_id for row in days)),
        (Day, sorted(row.pk for row in days)),
        (CupboardItem, sorted(row.pk for row in items)),
    ]


def test_bulk_null_intake_consumption_delete_locks_items_by_pk(
    mocker,
    food_product_factory,
    serving_factory,
    cupboard_item_factory,
):
    """Historical links without intakes still obtain deterministic item locks."""
    product = food_product_factory(size=100)
    serving = serving_factory(food=product, serving_size=10, serving_unit="g")
    items = [cupboard_item_factory(food=product) for _ in range(2)]
    consumptions = [
        CupboardItemConsumption.objects.create(
            item=item,
            serving=serving,
            intake=None,
            num_servings=Decimal("1"),
        )
        for item in items
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    CupboardItemConsumption.objects.filter(
        pk__in=[row.pk for row in consumptions]
    ).order_by("-pk").delete()

    assert locked_rows[0] == (
        CupboardItem,
        sorted(row.pk for row in items),
    )
