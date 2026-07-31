"""food recipes tests modules."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.foods.models import RecipeIngredient, Serving


def test_calculate_recipe_nutrients(db, recipe_ingredient):
    """Calculate recipe nutrients correctly."""
    # Given
    assert recipe_ingredient.food.protein_g == 25  # / 100 g
    assert recipe_ingredient.food.size == 100
    assert recipe_ingredient.protein_g == 25
    recipe = recipe_ingredient.recipe
    assert recipe.protein_g == 250

    # When
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # Then
    assert recipe.protein_g == 25
    assert recipe.servings.get().protein_g == Decimal("12.5")


def test_do_not_calculate_recipe_nutrients(db, recipe_ingredient):
    """Do not Calculate recipe nutrients when there is no change."""
    # Given
    recipe = recipe_ingredient.recipe
    assert recipe.protein_g == 250

    # When
    recipe.save()

    # Then
    assert recipe.protein_g == 250


def test_increase_recipe_nutrient(db, recipe_ingredient):
    """Increase recipe nutrient correctly."""
    # Given
    recipe = recipe_ingredient.recipe
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # When
    recipe_ingredient.num_servings = 2
    recipe_ingredient.save()

    # Then
    recipe.refresh_from_db()
    assert recipe.protein_g == 50


def test_decrease_recipe_nutrient(db, recipe_ingredient):
    """Decrease recipe nutrient correctly."""
    # Given
    recipe = recipe_ingredient.recipe
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # When
    recipe.ingredients.all().delete()

    # Then
    recipe.refresh_from_db()
    assert recipe.protein_g == 0


def test_do_not_decrease_recipe_nutrient(db, recipe_ingredient):
    """Do not decrease recipe nutrient correctly when there is no change."""
    # Given
    recipe = recipe_ingredient.recipe

    # When
    recipe.ingredients.all().delete()

    # Then
    recipe.refresh_from_db()
    assert recipe.protein_g == 250


def test_create_recipe_ingredient(db, recipe, recipe_ingredient_factory):
    """Create recipe ingredient correctly."""
    # Given
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # When
    ingredient = recipe_ingredient_factory(recipe=recipe)

    # Then
    assert ingredient.protein_g == 25


def test_recipe_ingredient_quantity_scales_recipe_mass(
    db, recipe, recipe_ingredient_factory, serving
):
    """Ingredient mass includes fractional and multiple serving quantities."""
    recipe.nutrients_from_ingredients = True
    recipe.save()

    recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2.5")
    )

    recipe.refresh_from_db()
    assert recipe.size == Decimal("250")


def test_recipe_ingredient_keeps_coherent_serving_snapshot(
    db, recipe, recipe_ingredient_factory, serving
):
    """Serving edits cannot mix new mass with old ingredient nutrients."""
    ingredient = recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2")
    )
    original = (ingredient.size, ingredient.protein_g)

    serving.serving_size = Decimal("50")
    serving.save()
    ingredient.refresh_from_db()

    assert (ingredient.size, ingredient.protein_g) == original


def test_legacy_null_recipe_snapshot_is_lazily_resolved(
    db, recipe, recipe_ingredient_factory, serving
):
    """Ingredients written during expansion remain readable before backfill."""
    ingredient = recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2")
    )
    type(ingredient).objects.filter(pk=ingredient.pk).update(
        size_snapshot=None, size_snapshot_unit=None
    )
    ingredient.refresh_from_db()

    assert ingredient.size == Decimal("200")
    assert ingredient.effective_size_snapshot_unit == "g"


def test_saving_legacy_null_recipe_snapshot_dual_writes_it(
    db, recipe, recipe_ingredient_factory, serving
):
    """A new writer fills a nullable ingredient snapshot on any model save."""
    ingredient = recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2")
    )
    type(ingredient).objects.filter(pk=ingredient.pk).update(
        size_snapshot=None, size_snapshot_unit=None
    )
    ingredient.refresh_from_db()

    ingredient.save(update_fields=["recipe"])

    ingredient.refresh_from_db()
    assert ingredient.size_snapshot == Decimal("200")
    assert ingredient.size_snapshot_unit == "g"


def test_recipe_aggregate_converts_mixed_mass_snapshot_units(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Recipe mass is converted instead of adding raw kilogram and gram values."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True,
        size=0,
        size_unit="g",
    )
    grams = food_product_factory(size=Decimal("100"), size_unit="g")
    kilograms = food_product_factory(size=Decimal("1"), size_unit="kg")
    gram_serving = Serving.objects.create(
        food=grams, serving_size=Decimal("250"), serving_unit="g"
    )
    kilogram_serving = Serving.objects.create(
        food=kilograms, serving_size=Decimal("1"), serving_unit="kg"
    )

    first = recipe_ingredient_factory(recipe=recipe, food=gram_serving)
    second = recipe_ingredient_factory(recipe=recipe, food=kilogram_serving)

    recipe.refresh_from_db()
    assert first.size_snapshot_unit == "g"
    assert second.size_snapshot_unit == "kg"
    assert recipe.size == Decimal("1250")


def test_recipe_ingredient_snapshot_survives_catalog_and_recipe_edits(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Unrelated saves never reinterpret a complete historical snapshot."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True,
        size=0,
        size_unit="g",
    )
    product = food_product_factory(
        size=Decimal("400"), size_unit="g", protein_g=Decimal("10")
    )
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("100"), serving_unit="g"
    )
    ingredient = recipe_ingredient_factory(recipe=recipe, food=serving)
    original = (
        ingredient.size_snapshot,
        ingredient.size_snapshot_unit,
        ingredient.protein_g,
    )

    serving.serving_size = Decimal("2")
    serving.serving_unit = "kg"
    serving.save()
    product.size = Decimal("3")
    product.size_unit = "kg"
    product.protein_g = Decimal("99")
    product.save()
    recipe.name = "Renamed"
    recipe.save(update_fields=["name"])
    ingredient.save(update_fields=["recipe"])

    ingredient.refresh_from_db()
    recipe.refresh_from_db()
    assert (
        ingredient.size_snapshot,
        ingredient.size_snapshot_unit,
        ingredient.protein_g,
    ) == original
    assert recipe.size == Decimal("100")


def test_recipe_aggregate_converts_mixed_volume_snapshot_units(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Compatible liquid snapshots are normalized to the recipe volume unit."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True,
        size=0,
        size_unit="ml",
        nutritional_info_unit="ml",
    )
    product = food_product_factory(
        size=Decimal("1"),
        size_unit="l",
        nutritional_info_unit="ml",
    )
    litre = Serving.objects.create(
        food=product, serving_size=Decimal("1"), serving_unit="l"
    )
    millilitres = Serving.objects.create(
        food=product, serving_size=Decimal("250"), serving_unit="ml"
    )

    recipe_ingredient_factory(recipe=recipe, food=litre)
    recipe_ingredient_factory(recipe=recipe, food=millilitres)

    recipe.refresh_from_db()
    assert recipe.size == Decimal("1250")


def test_recipe_ingredient_rejects_incompatible_snapshot_dimension(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """A mass recipe cannot persist a volume ingredient contribution."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True, size=0, size_unit="g"
    )
    product = food_product_factory(
        size=Decimal("1"),
        size_unit="l",
        nutritional_info_unit="ml",
    )
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("250"), serving_unit="ml"
    )

    with pytest.raises(ValidationError, match="incompatible"):
        recipe_ingredient_factory(recipe=recipe, food=serving)

    assert recipe.ingredients.count() == 0
    recipe.refresh_from_db()
    assert recipe.size == 0


@pytest.mark.parametrize("contextual_unit", ["container", "serving"])
def test_contextual_serving_snapshot_resolves_to_food_size_unit(
    db,
    contextual_unit,
    recipe_factory,
    food_product_factory,
    recipe_ingredient_factory,
):
    """Contextual serving labels are made concrete at ingredient write time."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True, size=0, size_unit="g"
    )
    product = food_product_factory(
        size=Decimal("600"), size_unit="g", num_servings=3
    )
    serving = product.servings.get(serving_unit=contextual_unit)

    ingredient = recipe_ingredient_factory(recipe=recipe, food=serving)

    recipe.refresh_from_db()
    assert ingredient.size_snapshot_unit == "g"
    assert recipe.size == (
        Decimal("600") if contextual_unit == "container" else Decimal("200")
    )


def test_recipe_size_unit_edit_reconverts_historical_snapshots(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Changing aggregate display unit preserves the ingredient's physical size."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True, size=0, size_unit="g"
    )
    product = food_product_factory(size=Decimal("1"), size_unit="kg")
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("1"), serving_unit="kg"
    )
    ingredient = recipe_ingredient_factory(recipe=recipe, food=serving)
    assert ingredient.size_snapshot == Decimal("1")

    recipe.size_unit = "kg"
    recipe.save(update_fields=["size_unit"])

    recipe.refresh_from_db()
    ingredient.refresh_from_db()
    assert recipe.size == Decimal("1")
    assert ingredient.size_snapshot == Decimal("1")
    assert ingredient.size_snapshot_unit == "kg"


def test_recipe_ingredient_create_locks_recipe_and_ingredients_before_write(
    db, mocker, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """A new contribution serializes on the recipe and existing ingredients."""
    recipe = recipe_factory(nutrients_from_ingredients=True, size=0)
    product = food_product_factory()
    serving = product.servings.first()
    recipe_lock = mocker.spy(type(recipe).objects, "select_for_update")
    ingredient_lock = mocker.spy(RecipeIngredient.objects, "select_for_update")

    recipe_ingredient_factory(recipe=recipe, food=serving)

    recipe_lock.assert_called()
    ingredient_lock.assert_called()
