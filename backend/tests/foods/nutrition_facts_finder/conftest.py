"""fixtures for nutrition_facts_finder tests."""

import pytest


@pytest.fixture
def gemini_api(mocker, request):
    """Gemini API mock."""
    mock = mocker.patch("apps.foods.nutrition_facts_finder.genai.Client")
    mock.return_value.models.generate_content.return_value.text = str(
        request.param
    )
    return mock
