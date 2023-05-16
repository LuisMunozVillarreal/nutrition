"""Food app tests."""


from apps.foods.models import Food


def test_food_no_brand(db, food_product_factory):
    """Food with no brand has a str representation."""
    # Given
    product = food_product_factory(brand=None)
    food = Food.objects.get(id=product.id)

    # When / Then
    assert str(food) == "Chicken Breast"
