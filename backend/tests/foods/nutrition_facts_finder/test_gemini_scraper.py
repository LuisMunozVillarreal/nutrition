"""Test Gemini scraper module."""

import pytest

from apps.foods.admin.product import FoodProductForm

from . import DEFAULT_FORM_DATA


@pytest.mark.parametrize(
    "gemini_api",
    (
        [
            {
                "kcal": 100,
                "fat": 10.1,
                "saturates": 10.1,
                "carbohydrates": 10.1,
                "sugars": 10.1,
                "fibre": 10.1,
                "protein": 10.1,
                "salt": 10.1,
            }
        ]
    ),
    indirect=True,
)
def test_get_nutrition_facts_with_gemini(gemini_api):
    """Get nutrition facts with gemini."""
    # Given the following form data
    data = {
        "name": "Chicken",
        "get_info_with_gemini": True,
        **DEFAULT_FORM_DATA,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And gemini has been called
    gemini_api.assert_called()
