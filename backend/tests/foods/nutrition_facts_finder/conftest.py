"""fixtures for nutrition_facts_finder tests."""

import pytest


@pytest.fixture
def gemini_api(mocker, request):
    """Gemini API mock."""
    mock = mocker.patch(
        "apps.foods.nutrition_facts_finder.genai.GenerativeModel"
    )
    mid_mock = mock.return_value.start_chat.return_value.send_message
    mid_mock.return_value.text = str(request.param)
    return mock
