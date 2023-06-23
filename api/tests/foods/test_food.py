"""Food app tests."""


from apps.foods.models import Food


def test_food_no_brand(db, food_product_factory):
    """Food with no brand has a str representation."""
    # Given
    product = food_product_factory(brand=None)
    food = Food.objects.get(id=product.id)

    # When / Then
    assert str(food) == "Chicken Breast"
    assert str(product) == "Chicken Breast (320g)"


def test_food_with_brand(db, food_product):
    """Food with brand has a str representation."""
    # Given
    food = Food.objects.get(id=food_product.id)

    # When / Then
    assert str(food) == "Ocado Chicken Breast"
    assert str(food_product) == "Ocado Chicken Breast (320g)"
