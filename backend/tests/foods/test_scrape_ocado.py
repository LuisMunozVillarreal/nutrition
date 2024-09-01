"""Tests ocado scraper moduel."""

import pytest

from apps.foods.admin.product import FoodProductForm

URL = "https://www.ocado.com/products/geeta-s-tikka-paste-207606011"


@pytest.fixture
def gemini_api(mocker):
    """Gemini API mock."""
    data = {
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
    mock = mocker.patch("apps.foods.ocado_scraper.genai.GenerativeModel")
    mid_mock = mock.return_value.start_chat.return_value.send_message
    mid_mock.return_value.text = str(data)
    return mock


@pytest.fixture
def ocado_request(requests_mock):
    """Ocado request mock."""
    return requests_mock.get(
        URL,
        status_code=200,
        text="<html><body>hola</body></html>",
    )


def test_ocado_scrapped(gemini_api, ocado_request):
    """Ocado is scrapped correctly."""
    # Given the following form data
    data = {
        "scrape_info_from_url": True,
        "url": URL,
        "energy": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbs_g": 0,
        "nutritional_info_size": 0,
        "nutritional_info_unit": "ml",
        "weight": 0,
        "weight_unit": "ml",
        "num_servings": 0,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And ocado has been scraped
    assert ocado_request.call_count == 1
    gemini_api.assert_called()


def test_ocado_not_scrapped(gemini_api, ocado_request):
    """Ocado is not scrapped."""
    # Given the following form data
    data = {
        "name": "Hola",
        "energy": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbs_g": 0,
        "nutritional_info_size": 0,
        "nutritional_info_unit": "ml",
        "weight": 0,
        "weight_unit": "ml",
        "num_servings": 0,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And ocado has not been scraped
    assert not ocado_request.called
    gemini_api.assert_not_called()


def test_ocado_missing_url(gemini_api, ocado_request):
    """Missing URL."""
    # Given the following form data
    data = {
        "scrape_info_from_url": True,
        "energy": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbs_g": 0,
        "nutritional_info_size": 0,
        "nutritional_info_unit": "ml",
        "weight": 0,
        "weight_unit": "ml",
        "num_servings": 0,
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


@pytest.fixture
def gemini_api_missing_info(mocker):
    """Gemini API missing info mock."""
    data = {
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
    mock = mocker.patch("apps.foods.ocado_scraper.genai.GenerativeModel")
    mid_mock = mock.return_value.start_chat.return_value.send_message
    mid_mock.return_value.text = str(data)
    return mock


def test_ocado_missing_info(gemini_api_missing_info, ocado_request):
    """Ocado scrapper can handle empty info values."""
    # Given the following form data
    data = {
        "scrape_info_from_url": True,
        "url": URL,
        "energy": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbs_g": 0,
        "nutritional_info_size": 0,
        "nutritional_info_unit": "ml",
        "weight": 0,
        "weight_unit": "ml",
        "num_servings": 0,
    }

    # When the form is created
    form = FoodProductForm(data=data)

    # Then the form is valid
    assert form.is_valid()

    # And ocado has been scraped
    assert ocado_request.call_count == 1
    gemini_api_missing_info.assert_called()
