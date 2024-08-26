"""Food product Ocado scraper."""

import ast
from typing import Any, Dict

import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from django.conf import settings


def get_ocado_product_details(url: str) -> Dict[str, Any | float]:
    """Get Ocado Product details.

    Args:
        url (str): URL to scrape the date from.

    Returns:
        Dict[str, str | float]
    """
    genai.configure(api_key=settings.GEMINI_API_KEY)

    # Create the model
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=generation_config,
        system_instruction="""
            You will receive an HTML code.
            That HTML is of an Ocado product.
            Extract information from that HTML.
            Return only code, no text or markdown language.
            Return that information as a python dictionary.
            Your answer can't contain "```python".
            Provide all values as numbers, except from the size unit.
            It's python, use None instead of null.
            That python dictionary should contain the following keys:
            - brand,
            - name (without the brand in it),
            - size,
            - size unit,
            - servings,
            - kcal,
            - fat,
            - saturates,
            - carbohydrates,
            - sugars,
            - fibre,
            - protein
            - salt.
        """,
    )

    # Scrape
    page = requests.get(url, timeout=60)
    soup = BeautifulSoup(page.content, "html.parser")
    body = soup.find("body")

    # Analyse
    chat_session = model.start_chat()
    response = chat_session.send_message(str(body))

    return ast.literal_eval(response.text)
