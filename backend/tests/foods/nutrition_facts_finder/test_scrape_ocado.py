"""Tests ocado scraper module."""

import pytest

from apps.foods.admin.product import FoodProductForm

from . import DEFAULT_FORM_DATA

URL = "https://www.ocado.com/products/geeta-s-tikka-paste-207606011"
GEMINI_DATA = {
    "brand": "Ocado",
    "name": "Chicken",
    "size": 100,
    "size unit": "ml",
    "servings": 1,
    "kcal": 100,
    "fat": 10.1,
    "saturates": 10.1,
    "carbohydrates": 10.1,
    "sugars": 10.1,
    "fibre": 10.1,
    "protein": 10.1,
    "salt": 10.1,
}


@pytest.fixture
def ocado_request(requests_mock):
    """Ocado request mock."""
    return requests_mock.get(
        URL,
        status_code=200,
        text="<html><body>hola</body></html>",
    )


@pytest.mark.parametrize("gemini_api", ([GEMINI_DATA]), indirect=True)
def test_ocado_scrapped(gemini_api, ocado_request):
    """Ocado is scrapped correctly."""
    # Given the following form data
    data = {
        "scrape_info_from_url": True,
        "url": URL,
        **DEFAULT_FORM_DATA,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And ocado has been scraped
    assert ocado_request.call_count == 1
    gemini_api.assert_called()


@pytest.mark.parametrize("gemini_api", ([GEMINI_DATA]), indirect=True)
def test_ocado_not_scrapped(gemini_api, ocado_request):
    """Ocado is not scrapped."""
    # Given the following form data
    data = {
        "name": "Hola",
        **DEFAULT_FORM_DATA,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And ocado has not been scraped
    assert not ocado_request.called
    gemini_api.assert_not_called()


@pytest.mark.parametrize("gemini_api", ([GEMINI_DATA]), indirect=True)
def test_ocado_missing_url(gemini_api, ocado_request):
    """Missing URL."""
    # Given the following form data
    data = {
        "scrape_info_from_url": True,
        **DEFAULT_FORM_DATA,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is not valid
    assert not form.is_valid()

    # And ocado has not been scraped
    assert not ocado_request.called
    gemini_api.assert_not_called()

    # And form shows the related error
    assert "URL is required" in str(form.errors)


def test_non_ocado_url():
    """Non Ocado URL fails."""
    # Given a non Ocado URLCONF
    data = {
        "scrape_info_from_url": True,
        "url": "https://anothersite.com/products/tomato",
    }

    # When the form is created
    form = FoodProductForm(data)

    # Then the for is not valid
    assert not form.is_valid()

    # And form shows the related error
    assert "Only Ocado product URLs are supported" in str(form.errors)


@pytest.mark.parametrize(
    "gemini_api",
    (
        [
            {
                "brand": None,
                "name": "hola",
                "size": None,
                "size unit": None,
                "servings": None,
                "kcal": None,
                "fat": None,
                "saturates": None,
                "carbohydrates": None,
                "sugars": None,
                "fibre": None,
                "protein": None,
                "salt": None,
            }
        ]
    ),
    indirect=True,
)
def test_ocado_missing_info(gemini_api, ocado_request):
    """Ocado scrapper can handle empty info values."""
    # Given the following form data
    data = {
        "scrape_info_from_url": True,
        "url": URL,
        **DEFAULT_FORM_DATA,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And ocado has been scraped
    assert ocado_request.call_count == 1
    gemini_api.assert_called()
