"""Focused residual coverage for food locking, models, and signals."""

# pylint: disable=protected-access

from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.db import models

from apps.foods.cupboard_locks import (
    CupboardItemLocks,
    activate_cupboard_item_locks,
    lock_cupboard_items,
)
from apps.foods.deletion import (
    NutritionDeletionLocks,
    activate_nutrition_deletion_locks,
    lock_nutrition_deletion,
)
from apps.foods.models import CupboardItem, CupboardItemConsumption, Recipe
from apps.foods.models.recipe import (
    RecipeIngredient,
    _RecipeIngredientOwnerChanged,
)
from apps.foods.models.units import UNIT_CONTAINER
from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
    _get_consumed_amount,
    _get_consumed_perc,
    _intake_cupboard_item,
    _lock_cupboard_item,
    control_finished_items,
    recalculate_consumed_perc,
)
from apps.foods.signals.handlers.recipe_nutrients import (
    _size_in_recipe_unit,
    increase_recipe_nutrients,
)
from apps.libs.graphql import validated_positive_decimal


def test_nested_cupboard_lock_bundle_reuses_or_rejects_active_scope():
    """Cover nested cupboard lock bundle reuses or rejects active scope."""
    locks = CupboardItemLocks("default", {1: object()})

    with activate_cupboard_item_locks(locks):
        assert lock_cupboard_items([1], "default") is locks
        with pytest.raises(RuntimeError, match="cannot expand"):
            lock_cupboard_items([1, 2], "default")


def test_deletion_lock_activation_includes_cupboard_context(mocker):
    """Cover deletion lock activation includes cupboard context."""
    entered = []

    # Real context manager factories are replaced with observable null contexts.
    mocker.patch(
        "apps.foods.cupboard_locks.activate_cupboard_item_locks",
        side_effect=lambda value: entered.append(("cupboard", value))
        or nullcontext(),
    )
    locks = NutritionDeletionLocks(None, None, object(), None)

    with activate_nutrition_deletion_locks(locks):
        pass

    assert entered == [("cupboard", locks.cupboard_locks)]

    with activate_nutrition_deletion_locks(
        NutritionDeletionLocks(None, None, None, None)
    ):
        pass


def test_unrelated_deletion_targets_need_no_nutrition_locks(mocker):
    """Cover unrelated deletion targets need no nutrition locks."""
    targets = SimpleNamespace(model=type("Other", (), {}))
    mocker.patch(
        "apps.foods.deletion.apps.get_model",
        side_effect=[
            type("Serving", (), {}),
            type("Food", (), {}),
            object(),
            type("Consumption", (), {}),
        ],
    )

    result = lock_nutrition_deletion(targets, "default")

    assert result == NutritionDeletionLocks(None, None, None, None)


def test_cupboard_item_new_manual_baseline_preservation(mocker):
    """Cover cupboard item new manual baseline preservation."""
    persisted = mocker.patch.object(models.Model, "save")
    for manual, consumed in [
        (Decimal("10"), Decimal("10")),
        (Decimal("0"), Decimal("10")),
    ]:
        item = CupboardItem(
            consumed_perc=consumed, manual_consumed_perc=manual
        )
        item.save()

    assert persisted.call_count == 2


def _existing_cupboard_item(mocker, previous, **values):
    item = CupboardItem(pk=1, **values)
    item._state.adding = False
    queryset = mocker.patch.object(
        CupboardItem.objects, "select_for_update"
    ).return_value
    queryset.using.return_value.select_related.return_value.get.return_value = (
        previous
    )
    mocker.patch.object(models.Model, "save")
    return item


def test_cupboard_item_update_adds_reconciled_manual_field(mocker):
    """Cover cupboard item update adds reconciled manual field."""
    previous = SimpleNamespace(
        manual_consumed_perc=Decimal("10"), consumed_perc=Decimal("20")
    )
    item = _existing_cupboard_item(
        mocker,
        previous,
        consumed_perc=Decimal("20"),
        manual_consumed_perc=None,
    )

    item.save(update_fields={"consumed_perc"})

    assert item.manual_consumed_perc == Decimal("10")


def test_cupboard_item_update_rejects_below_linked_and_tracks_manual(mocker):
    """Cover cupboard item update rejects below linked and tracks manual."""
    previous = SimpleNamespace(
        manual_consumed_perc=Decimal("10"), consumed_perc=Decimal("30")
    )
    below = _existing_cupboard_item(
        mocker,
        previous,
        consumed_perc=Decimal("15"),
        manual_consumed_perc=Decimal("10"),
    )
    with pytest.raises(ValueError, match="linked consumption"):
        below.save(update_fields={"consumed_perc"})

    updated = _existing_cupboard_item(
        mocker,
        previous,
        consumed_perc=Decimal("40"),
        manual_consumed_perc=Decimal("10"),
    )
    updated.save(update_fields={"consumed_perc"})
    assert updated.manual_consumed_perc == Decimal("20")


def test_nullable_consumption_quantity_uses_linked_intake():
    """Cover nullable consumption quantity uses linked intake."""
    intake = SimpleNamespace(num_servings=Decimal("2.5"))
    consumption = CupboardItemConsumption(num_servings=None)
    consumption.intake_id = 1
    consumption._state.fields_cache["intake"] = intake

    assert consumption.resolved_num_servings == Decimal("2.5")


def test_recipe_refresh_field_selection_branches(mocker):
    """Cover recipe refresh field selection branches."""
    recipe = Recipe()
    recipe.get_deferred_fields = mocker.Mock(return_value={"fat_g"})
    only = mocker.Mock()
    only.query.deferred_loading = ({"size", "protein_g"}, False)
    queryset = mocker.Mock()
    queryset.only.return_value = only

    selected = recipe._refreshed_protected_write_fields({"size"}, queryset)
    assert selected == {"size"}
    queryset.only.assert_called_once_with("size")

    deferred_query = mocker.Mock()
    deferred_query.query.deferred_loading = ({"fat_g"}, True)
    queryset.only.reset_mock()
    queryset.only.return_value = deferred_query
    selected = recipe._refreshed_protected_write_fields(None, queryset)
    assert "fat_g" not in selected
    queryset.only.assert_called_once()

    empty = mocker.Mock()
    empty.query.deferred_loading = (set(), False)
    queryset.only.return_value = empty
    assert recipe._refreshed_protected_write_fields({"size"}, queryset) == {
        "size"
    }


def test_recipe_save_detects_deletion_after_lock(mocker):
    """Cover recipe save detects deletion after lock."""
    recipe = Recipe(pk=9, name="gone", num_servings=1)
    mocker.patch(
        "apps.foods.recipe_locks.lock_recipe_ingredients",
        return_value=({}, ()),
    )

    with pytest.raises(Recipe.DoesNotExist, match="deleted"):
        recipe.save()


def test_contextual_recipe_ingredient_snapshot_uses_base_food_unit():
    """Cover contextual recipe ingredient snapshot uses base food unit."""
    ingredient = RecipeIngredient(size_snapshot_unit=None)
    ingredient._state.fields_cache["food"] = SimpleNamespace(
        serving_unit=UNIT_CONTAINER,
        food=SimpleNamespace(size_unit="g"),
    )

    assert ingredient.effective_size_snapshot_unit == "g"


def test_recipe_ingredient_owner_resolution_branches(mocker):
    """Cover recipe ingredient owner resolution branches."""
    ingredient = RecipeIngredient(pk=5, recipe_id=1, num_servings=1)
    ingredient._state.adding = False
    manager = mocker.Mock()
    using_manager = manager.using.return_value
    using_manager.filter.return_value.values_list.return_value.first.return_value = (
        1
    )
    manager.select_for_update.return_value.using.return_value.get.side_effect = (
        RecipeIngredient.DoesNotExist
    )
    mocker.patch.object(RecipeIngredient, "objects", manager)
    mocker.patch(
        "apps.foods.recipe_locks.lock_recipe_ingredients",
        return_value=({1: Recipe(pk=1)}, ()),
    )

    with pytest.raises(RecipeIngredient.DoesNotExist):
        ingredient._save_with_provisional_owners("default")

    current = SimpleNamespace(recipe_id=2)
    manager.select_for_update.return_value.using.return_value.get.side_effect = (
        None
    )
    manager.select_for_update.return_value.using.return_value.get.return_value = (
        current
    )
    with pytest.raises(_RecipeIngredientOwnerChanged):
        ingredient._save_with_provisional_owners("default")


def test_recipe_ingredient_owner_resolution_success_paths(mocker):
    """Owner resolution accepts a concurrent create and a stable existing owner."""
    target = Recipe(pk=1)
    manager = mocker.Mock()
    using_manager = manager.using.return_value
    using_manager.filter.return_value.values_list.return_value.first.return_value = (
        1
    )
    mocker.patch.object(RecipeIngredient, "objects", manager)
    mocker.patch(
        "apps.foods.recipe_locks.lock_recipe_ingredients",
        return_value=({1: target}, ()),
    )
    mocker.patch.object(
        RecipeIngredient, "_prepare_snapshots", return_value=None
    )
    mocker.patch.object(models.Model, "save")
    mocker.patch(
        "apps.foods.signals.handlers.recipe_nutrients.validate_recipe_ingredient_size"
    )
    mocker.patch(
        "apps.foods.signals.handlers.recipe_nutrients.recompute_recipe_nutrients"
    )

    concurrent_create = RecipeIngredient(pk=5, recipe_id=1, num_servings=1)
    manager.select_for_update.return_value.using.return_value.get.side_effect = (
        RecipeIngredient.DoesNotExist
    )
    recipes, observer = concurrent_create._save_with_provisional_owners(
        "default"
    )
    assert recipes == {1: target}
    assert observer is None

    stable = RecipeIngredient(pk=6, recipe_id=1, num_servings=1)
    stable._state.adding = False
    current = RecipeIngredient(pk=6, recipe_id=1, num_servings=1)
    manager.select_for_update.return_value.using.return_value.get.side_effect = (
        None
    )
    manager.select_for_update.return_value.using.return_value.get.return_value = (
        current
    )
    recipes, _ = stable._save_with_provisional_owners("default")
    assert recipes == {1: target}
    assert stable.recipe is target


def test_recipe_ingredient_save_retries_owner_change(mocker):
    """Standalone writes retry a provisional owner change in a fresh transaction."""
    ingredient = RecipeIngredient(recipe_id=1, num_servings=1)
    target = Recipe(pk=1)
    mocker.patch(
        "apps.foods.models.recipe.transaction.get_connection",
        return_value=SimpleNamespace(in_atomic_block=False),
    )
    mocker.patch(
        "apps.foods.models.recipe.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    save_attempt = mocker.patch.object(
        RecipeIngredient,
        "_save_with_provisional_owners",
        side_effect=[_RecipeIngredientOwnerChanged, ({1: target}, None)],
    )
    synchronize = mocker.patch(
        "apps.foods.signals.handlers.recipe_nutrients.synchronize_recipe_aggregates"
    )

    ingredient.save(using="default")

    assert save_attempt.call_count == 2
    synchronize.assert_not_called()


def test_recipe_ingredient_save_surfaces_owner_change_in_outer_transaction(
    mocker,
):
    """Cover recipe ingredient save surfaces owner change in outer transaction."""
    ingredient = RecipeIngredient(recipe_id=1, num_servings=1)
    mocker.patch(
        "apps.foods.models.recipe.transaction.get_connection",
        return_value=SimpleNamespace(in_atomic_block=True),
    )
    mocker.patch(
        "apps.foods.models.recipe.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    mocker.patch.object(
        RecipeIngredient,
        "_save_with_provisional_owners",
        side_effect=_RecipeIngredientOwnerChanged,
    )

    with pytest.raises(RuntimeError, match="owner changed"):
        ingredient.save(using="default")


def test_cupboard_signal_unit_and_limit_edges(mocker):
    """Cover cupboard signal unit and limit edges."""
    serving = SimpleNamespace(
        serving_unit=UNIT_CONTAINER,
        size_unit="g",
        size=Decimal("2"),
    )
    assert _get_consumed_amount(serving, Decimal("3")) == (Decimal("6"), "g")
    concrete = SimpleNamespace(
        serving_unit="g", size_unit="g", size=Decimal("2")
    )
    assert _get_consumed_amount(concrete, Decimal("3")) == (
        Decimal("6"),
        "g",
    )

    food = SimpleNamespace(size_unit=UNIT_CONTAINER, size=1)
    with pytest.raises(ValueError, match="incompatible"):
        _get_consumed_perc(food, Decimal("1"), "serving")

    item = SimpleNamespace(
        pk=1,
        consumed_perc=Decimal("101"),
        manual_consumed_perc=Decimal("101"),
    )
    mocker.patch(
        "apps.foods.signals.handlers.cupboard._reconcile_manual_consumed_perc",
        return_value=(Decimal("0"), False),
    )
    mocker.patch(
        "apps.foods.signals.handlers.cupboard.router.db_for_write",
        return_value="default",
    )
    mocker.patch(
        "apps.foods.signals.handlers.cupboard.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    with pytest.raises(CupboardItemConsumptionTooBigError):
        recalculate_consumed_perc(item, already_locked=True)


def test_intake_cupboard_lookup_edges(mocker):
    """Cover intake cupboard lookup edges."""
    assert _intake_cupboard_item(SimpleNamespace(food=None), "default") is None

    locks = SimpleNamespace(using="other", items_by_pk={})
    mocker.patch(
        "apps.foods.cupboard_locks.get_cupboard_item_locks",
        return_value=locks,
    )
    instance = SimpleNamespace(food=SimpleNamespace(food_id=1))
    with pytest.raises(RuntimeError, match="another database"):
        _intake_cupboard_item(instance, "default")

    mocker.patch(
        "apps.foods.cupboard_locks.get_cupboard_item_locks", return_value=None
    )
    queryset = mocker.Mock()
    mocker.patch.object(CupboardItem.objects, "using", return_value=queryset)
    expected = mocker.Mock()
    queryset.filter.return_value.order_by.return_value.first.return_value = (
        expected
    )
    instance = SimpleNamespace(
        food=SimpleNamespace(food_id=1),
        day=SimpleNamespace(plan=SimpleNamespace(user_id=2)),
    )
    assert _intake_cupboard_item(instance, "default") is expected


def test_locked_cupboard_write_rejects_uncovered_and_invalid_context(mocker):
    """Cover locked cupboard write rejects uncovered and invalid context."""
    locks = SimpleNamespace(covers=lambda *_args: False)
    mocker.patch(
        "apps.foods.cupboard_locks.get_cupboard_item_locks",
        return_value=locks,
    )
    instance = SimpleNamespace(item_id=3)
    with pytest.raises(RuntimeError, match="does not cover"):
        _lock_cupboard_item(instance, "default")

    item = SimpleNamespace(pk=3)
    instance = SimpleNamespace(
        item_id=3,
        id=None,
        _locked_cupboard_item=("other", item),
    )
    with pytest.raises(RuntimeError, match="invalid prelocked"):
        control_finished_items(None, instance, using="default")


def test_recipe_nutrient_context_and_compatibility_entrypoint(mocker):
    """Cover recipe nutrient context and compatibility entrypoint."""
    ingredient = SimpleNamespace(
        effective_size_snapshot_unit=UNIT_CONTAINER,
        recipe=mocker.Mock(),
    )
    recipe = SimpleNamespace(size_unit="g")
    with pytest.raises(ValidationError, match="concrete"):
        _size_in_recipe_unit(ingredient, recipe)

    rebuild = mocker.patch(
        "apps.foods.signals.handlers.recipe_nutrients.recompute_recipe_nutrients"
    )
    increase_recipe_nutrients(None, ingredient, using="other")
    rebuild.assert_called_once_with(ingredient.recipe, "other")


def test_positive_decimal_without_model_field():
    """Cover positive decimal without model field."""
    assert validated_positive_decimal(1.25, "value") == Decimal("1.25")
