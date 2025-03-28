"""food product servings tests module."""

from decimal import Decimal


def test_proudct_defualt_three_servings(db, food_product):
    """Product get three servings on creation."""
    # Then
    assert food_product.servings.count() == 4

    serving = food_product.servings.all()[0]
    assert serving.serving_size == 100
    assert serving.serving_unit == "g"
    assert serving.energy_kcal == 106

    serving = food_product.servings.all()[1]
    assert serving.serving_size == 1
    assert serving.serving_unit == "g"
    assert serving.energy_kcal == Decimal("1.06")

    serving = food_product.servings.all()[2]
    assert serving.serving_size == 1
    assert serving.serving_unit == "container"
    assert serving.energy_kcal == Decimal("339.2")

    serving = food_product.servings.all()[3]
    assert serving.serving_size == 1
    assert serving.serving_unit == "serving"
    assert serving.energy_kcal == Decimal("169.6")


def test_proudct_defualt_two_servings(db, food_product_factory):
    """Product get two servings on creation."""
    # When
    food_product = food_product_factory(
        nutritional_info_size=1,
    )

    # Then
    assert food_product.servings.count() == 3

    serving = food_product.servings.all()[0]
    assert serving.serving_size == 1
    assert serving.serving_unit == "g"
    assert serving.energy_kcal == Decimal("106")

    serving = food_product.servings.all()[1]
    assert serving.serving_size == 1
    assert serving.serving_unit == "container"
    assert serving.energy_kcal == Decimal("33920")


def test_product_one_servings(db, food_product_factory):
    """Product get one servings on creation."""
    # When
    food_product = food_product_factory(
        num_servings=1,
    )

    # Then
    assert food_product.servings.count() == 3


def test_product_different_container_unit(db, food_product_factory):
    """Serving is created correctly when the container unit is different."""
    # When
    food_product = food_product_factory(size_unit="kg")

    # Then
    serving = food_product.servings.all()[2]
    assert serving.serving_size == 1
    assert serving.serving_unit == "container"
    assert serving.energy_kcal == Decimal("339200")


def test_product_save_no_more_servings(db, food_product):
    """Already created product doesn't create more servings when saved."""
    # Given
    assert food_product.servings.count() == 4

    # When
    food_product.save()

    # Then
    assert food_product.servings.count() == 4


def test_product_update_nutrition_on_servings(db, food_product):
    """Nutritional info is updated on the servings when the size changes."""
    # When
    food_product.nutritional_info_size = 200
    food_product.save()

    # Then
    serving = food_product.servings.all()[0]
    assert serving.energy_kcal == 53


def test_product_update_size_on_servings(db, food_product):
    """Size change is reflected on the nutrients."""
    # When
    food_product.size = 640
    food_product.save()

    # Then
    serving = food_product.servings.all()[2]
    assert serving.energy_kcal == Decimal("678.4")
