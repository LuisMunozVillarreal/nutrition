"""Food product nutrition facts finder module."""

import ast
from typing import Any, Dict

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from google import genai
from google.genai import types


def get_product_nutritional_info_from_url(url: str) -> Dict[str, Any | float]:
    """Get product nutritional information from URL.

    Use https://aistudio.google.com/ to tweak the prompt.

    Args:
        url (str): URL to scrape the date from.

    Returns:
        Dict[str, str | float]
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

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

    # Analyse
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
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
        """
        ),
        contents=[str(html)],  # type: ignore[arg-type]
    )

    if response.text is None:  # pragma: no cover
        return {}
    return ast.literal_eval(response.text)


def get_food_nutrition_facts(food: str) -> Dict[str, float]:
    """Get food nutrition facts.

    Args:
        food (str): Food to get the nutrition facts from.

    Returns:
        Dict[str, float]
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Analyse
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
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
        """
        ),
        contents=[food],  # type: ignore[arg-type]
    )

    if response.text is None:  # pragma: no cover
        return {}
    return ast.literal_eval(response.text)
