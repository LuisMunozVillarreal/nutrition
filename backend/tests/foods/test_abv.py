"""Tests for ABV conversion."""

from decimal import Decimal


def test_abv_to_kcals(food_factory):
    """ABV to kcal."""
    # When a beer's ABV% is 5
    food = food_factory(
        abv_perc=Decimal("3.8"),
        nutritional_info_size=Decimal("100"),
        nutritional_info_unit="ml",
        size=Decimal("330"),
        size_unit="ml",
    )

    # Then its kcals are correct
    assert food.energy_kcal == Decimal("32.1233215667508595000")
