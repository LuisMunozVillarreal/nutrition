"""Food product nutrition facts finder module."""

import ast
from typing import Any, Dict

# TODO: Remove this when the stubs are available - pylint: disable=fixme
import google.generativeai as genai  # type: ignore[import-untyped]
import requests
from bs4 import BeautifulSoup
from django.conf import settings


def get_product_nutritional_info_from_url(url: str) -> Dict[str, Any | float]:
    """Get product nutritional information from URL.

    Use https://aistudio.google.com/ to tweak the prompt.

    Args:
        url (str): URL to scrape the date from.

    Returns:
        Dict[str, str | float]
    """
    genai.configure(api_key=settings.GEMINI_API_KEY)

    # Create the model
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction="""
            You will receive an HTML page.
            This page might contain javascript.
            That page contains information of a food product.
            Extract information from that page.
            Return only code, no text or markdown language.
            Return that information as a python dictionary.
            Your answer can't contain "```python".
            Provide all values as numbers, except from the size unit.
            Use international units for the size unit.
            It's python, use None instead of null.
            That python dictionary should contain the following keys:
            - brand
            - name (without the brand in it)
            - size
            - size unit
            - servings
            - kcal
            - fat
            - saturates
            - carbohydrates
            - sugars
            - fibre
            - protein
            - salt
        """,
    )

    # Scrape
    page = requests.get(
        url,
        timeout=60,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            ),
        },
    )
    soup = BeautifulSoup(page.content, "html.parser")
    html = soup.find("html")
    print(html)

    # Analyse
    chat_session = model.start_chat()
    response = chat_session.send_message(str(html))

    return ast.literal_eval(response.text)


def get_food_nutrition_facts(food: str) -> Dict[str, float]:
    """Get food nutrition facts.

    Args:
        food (str): Food to get the nutrition facts from.

    Returns:
        Dict[str, float]
    """
    genai.configure(api_key=settings.GEMINI_API_KEY)

    # Create the model
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction="""
            I'll give you the name of a food and I need you to give me a
            python dictionary with the nutritional facts for 100 grams of
            such food.
            Only a python dictionary, I don't need any additional text.
            Your answer can't contain "```python".
            The dictionary should have the following keys:
            - kcal
            - fat
            - saturates
            - carbohydrates
            - sugars
            - fibre
            - protein
            - salt
        """,
    )

    # Analyse
    chat_session = model.start_chat()
    response = chat_session.send_message(food)

    return ast.literal_eval(response.text)
