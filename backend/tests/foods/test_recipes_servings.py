"""recipe servings tests module."""


def test_recipe_serving(db, recipe_factory):
    """Serving is created on recipe creation."""
    # When
    recipe = recipe_factory(num_servings=6, energy=600)

    # Then
    assert recipe.servings.count() == 1
    assert recipe.servings.first().energy == 100


def test_recipe_save_no_more_servings(db, recipe):
    """Save an already created recipe doesn't create more servings."""
    # Given
    assert recipe.servings.count() == 1

    # When
    recipe.save()

    # Then
    assert recipe.servings.count() == 1


def test_update_recipe_serving_nutrients(db, recipe):
    """Update recipe reflect changes in its serving."""
    # Given
    assert recipe.servings.first().energy == 530

    # When
    recipe.energy = 500
    recipe.save()

    # Then
    assert recipe.servings.first().energy == 250
