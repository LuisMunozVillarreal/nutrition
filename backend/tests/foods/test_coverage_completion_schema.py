"""Focused residual branch coverage for the foods GraphQL schema."""

# pylint: disable=too-many-arguments,too-many-positional-arguments

from types import SimpleNamespace

import pytest

from apps.foods.models import (
    Food,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)
from apps.foods.schema import (
    CupboardMutation,
    CupboardQuery,
    FoodMutation,
    FoodProductType,
    FoodQuery,
    RecipeMutation,
    RecipeQuery,
    RecipeType,
)

pytestmark = pytest.mark.django_db


def _info(user):
    return SimpleNamespace(
        context=SimpleNamespace(request=SimpleNamespace(user=user))
    )


def _staff():
    return SimpleNamespace(is_authenticated=True, is_staff=True)


def _user():
    return SimpleNamespace(is_authenticated=True)


@pytest.mark.parametrize("query_name", ["food_products", "recipes"])
def test_catalog_lists_reject_helper_returning_unauthenticated_user(
    mocker, query_name
):
    """Redundant resolver guards still fail closed for malformed helpers."""
    mocker.patch(
        "apps.foods.schema.get_request_user",
        return_value=SimpleNamespace(is_authenticated=False),
    )
    query = FoodQuery() if query_name == "food_products" else RecipeQuery()

    assert getattr(query, query_name)(_info(None)) == []


@pytest.mark.parametrize(
    ("query", "resolver"),
    [
        (FoodQuery(), "food_product"),
        (RecipeQuery(), "recipe"),
        (CupboardQuery(), "cupboard_item"),
    ],
)
def test_single_item_queries_reject_helper_returning_unauthenticated_user(
    mocker, query, resolver
):
    """Single-object queries fail closed even for malformed helper output."""
    mocker.patch(
        "apps.foods.schema.get_request_user",
        return_value=SimpleNamespace(is_authenticated=False),
    )

    assert getattr(query, resolver)(_info(None), "1") is None


def test_cupboard_list_rejects_helper_returning_unauthenticated_user(mocker):
    """Cover cupboard list rejects helper returning unauthenticated user."""
    mocker.patch(
        "apps.foods.schema.get_request_user",
        return_value=SimpleNamespace(is_authenticated=False),
    )

    assert CupboardQuery().cupboard_items(_info(None)) == []


def test_food_product_query_success_and_missing_paths(mocker):
    """Cover food product query success and missing paths."""
    obj = mocker.Mock()
    mapped = mocker.Mock()
    mocker.patch.object(FoodProduct.objects, "get", return_value=obj)
    converter = mocker.patch.object(
        FoodProductType, "from_model", return_value=mapped
    )

    assert FoodQuery().food_product(_info(_user()), "1") is mapped
    converter.assert_called_once_with(obj)

    mocker.patch.object(
        FoodProduct.objects, "get", side_effect=FoodProduct.DoesNotExist
    )
    assert FoodQuery().food_product(_info(_user()), "404") is None


def test_recipe_query_missing_path(mocker):
    """Cover recipe query missing path."""
    mocker.patch.object(Recipe.objects, "get", side_effect=Recipe.DoesNotExist)

    assert RecipeQuery().recipe(_info(_user()), "404") is None


def test_food_product_type_servings_converts_ordered_models(mocker):
    """Cover food product type servings converts ordered models."""
    serving = mocker.Mock()
    queryset = mocker.Mock()
    queryset.order_by.return_value = [serving]
    mocker.patch.object(Serving.objects, "filter", return_value=queryset)
    mapped = mocker.Mock()
    converter = mocker.patch(
        "apps.foods.schema.ServingType.from_model", return_value=mapped
    )
    value = SimpleNamespace(id=7)

    assert FoodProductType.servings(value) == [mapped]
    converter.assert_called_once_with(serving)


def test_recipe_type_ingredients_converts_ordered_models(mocker):
    """Cover recipe type ingredients converts ordered models."""
    ingredient = mocker.Mock()
    queryset = mocker.Mock()
    queryset.order_by.return_value = [ingredient]
    mocker.patch.object(
        RecipeIngredient.objects, "filter", return_value=queryset
    )
    mapped = mocker.Mock()
    converter = mocker.patch(
        "apps.foods.schema.RecipeIngredientType.from_model",
        return_value=mapped,
    )
    value = SimpleNamespace(id=8)

    assert RecipeType.ingredients(value) == [mapped]
    converter.assert_called_once_with(ingredient)


def test_update_food_product_missing_and_explicit_url_paths(mocker):
    """Cover update food product missing and explicit url paths."""
    mutation = FoodMutation()
    info = _info(_staff())
    mocker.patch.object(
        FoodProduct.objects, "get", side_effect=FoodProduct.DoesNotExist
    )
    with pytest.raises(ValueError, match="FoodProduct not found"):
        mutation.update_food_product(info, "404", "missing")

    obj = mocker.Mock()
    obj.servings.values_list.return_value = []
    mocker.patch.object(FoodProduct.objects, "get", return_value=obj)
    mapped = mocker.Mock()
    mocker.patch.object(FoodProductType, "from_model", return_value=mapped)

    assert (
        mutation.update_food_product(
            info, "1", "renamed", url="https://example.com/product"
        )
        is mapped
    )
    assert obj.url == "https://example.com/product"
    obj.save.assert_called_once_with()


@pytest.mark.parametrize(
    ("resolver", "model", "kwargs", "message"),
    [
        (
            "delete_food_product",
            FoodProduct,
            {"id": "404"},
            "FoodProduct not found",
        ),
        (
            "create_serving",
            Food,
            {"food_id": "404", "serving_size": 1, "serving_unit": "g"},
            "Food not found",
        ),
        (
            "update_serving",
            Serving,
            {"id": "404", "serving_size": 1, "serving_unit": "g"},
            "Serving not found",
        ),
        ("delete_serving", Serving, {"id": "404"}, "Serving not found"),
    ],
)
def test_food_mutations_translate_missing_models(
    mocker, resolver, model, kwargs, message
):
    """Cover food mutations translate missing models."""
    manager = model.objects
    if resolver == "update_serving":
        queryset = mocker.patch.object(manager, "select_related").return_value
        queryset.get.side_effect = model.DoesNotExist
    else:
        mocker.patch.object(manager, "get", side_effect=model.DoesNotExist)

    with pytest.raises(ValueError, match=message):
        getattr(FoodMutation(), resolver)(_info(_staff()), **kwargs)


@pytest.mark.parametrize(
    ("resolver", "model", "kwargs", "message", "select_for_update"),
    [
        (
            "update_recipe",
            Recipe,
            {"id": "404", "name": "missing"},
            "Recipe not found",
            True,
        ),
        ("delete_recipe", Recipe, {"id": "404"}, "Recipe not found", False),
        (
            "update_recipe_ingredient",
            RecipeIngredient,
            {"id": "404", "food_id": "1"},
            "RecipeIngredient not found",
            False,
        ),
        (
            "delete_recipe_ingredient",
            RecipeIngredient,
            {"id": "404"},
            "RecipeIngredient not found",
            False,
        ),
    ],
)
def test_recipe_mutations_translate_missing_models(
    mocker, resolver, model, kwargs, message, select_for_update
):
    """Cover recipe mutations translate missing models."""
    if select_for_update:
        queryset = mocker.patch.object(
            model.objects, "select_for_update"
        ).return_value
        queryset.get.side_effect = model.DoesNotExist
    else:
        mocker.patch.object(
            model.objects, "get", side_effect=model.DoesNotExist
        )

    with pytest.raises(ValueError, match=message):
        getattr(RecipeMutation(), resolver)(_info(_staff()), **kwargs)


@pytest.mark.parametrize(
    ("resolver", "kwargs"),
    [
        (
            "create_cupboard_item",
            {"food_id": "1", "purchased_at": "2026-01-01"},
        ),
        ("update_cupboard_item", {"id": "1", "consumed_perc": 10}),
        ("delete_cupboard_item", {"id": "1"}),
    ],
)
def test_cupboard_mutations_reject_helper_returning_unauthenticated_user(
    mocker, resolver, kwargs
):
    """Cover cupboard mutations reject helper returning unauthenticated user."""
    mocker.patch(
        "apps.foods.schema.get_request_user",
        return_value=SimpleNamespace(is_authenticated=False),
    )

    with pytest.raises(PermissionError, match="Authentication required"):
        getattr(CupboardMutation(), resolver)(_info(None), **kwargs)


def test_create_cupboard_item_translates_missing_food(mocker):
    """Cover create cupboard item translates missing food."""
    mocker.patch.object(Food.objects, "get", side_effect=Food.DoesNotExist)

    with pytest.raises(ValueError, match="Food not found"):
        CupboardMutation().create_cupboard_item(
            _info(_user()), "404", "2026-01-01"
        )
