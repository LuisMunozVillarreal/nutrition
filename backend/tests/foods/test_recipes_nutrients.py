"""food recipes tests modules."""

from decimal import Decimal


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
