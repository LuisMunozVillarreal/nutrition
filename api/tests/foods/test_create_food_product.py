"""Tests for the Food Product mutation create_food_product. """


import json
import pytest
from graphene_django.utils.testing import graphql_query


@pytest.fixture
def client_query(client):
    def func(*args, **kwargs):
        return graphql_query(*args, **kwargs, client=client)
    return func


def test_barcode_exists_in_db(client_query, db, food_product):
    """Barcode sent exists in DB."""
    # When
    response = client_query(
        """
        mutation {{
          createFoodProduct(
            barcode: "{}",
          ) {{
            foodProduct {{
              id
              brand
              name
              url
              barcode
              energy
              weight
              weightUnit
              numServings
              proteinG
              fatG
              saturatedFatG
              polyunsaturatedFatG
              monosaturatedFatG
              transFatG
              carbsG
              fiberCarbsG
              sugarCarbsG
              sodiumMg
              potassiumMg
              vitaminAPerc
              vitaminCPerc
              calciumPerc
              ironPerc
            }}
            state
          }}
        }}
        """.format(food_product.barcode),
    )

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    product = content["data"]["createFoodProduct"]
    assert product["state"] == "ALREADY_EXISTS"
    assert product["foodProduct"] == {
        "id": "1",
        "brand": "Ocado",
        "name": "Chicken Breast",
        "url": "http://foodproduct.link",
        "barcode": "012308980493",
        "energy": "106.0",
        "weight": 320,
        "weightUnit": "G",
        "numServings": "2.0",
        "proteinG": "25.0",
        "fatG": "0.5",
        "saturatedFatG": "0.0",
        "polyunsaturatedFatG": "0.0",
        "monosaturatedFatG": "0.0",
        "transFatG": "0.0",
        "carbsG": "0.3",
        "fiberCarbsG": "0.0",
        "sugarCarbsG": "0.0",
        "sodiumMg": "0.0",
        "potassiumMg": "0.0",
        "vitaminAPerc": 0,
        "vitaminCPerc": 0,
        "calciumPerc": 0,
        "ironPerc": 0,
    }


def test_only_barcode_is_sent(client_query):
    """Barcode sent doesn't exist in DB and no other field is sent."""


def test_barcode_in_openfoodfacts(client_query):
    """Barcode sent doesn't exist in DB, but in openfoodfacts."""


def test_barcode_not_in_openfoodfacts(client_query):
    """Barcode sent doesn't exist in DB, neither in openfoodfacts."""


def test_create_product_from_form(client_query):
    """Create food product from the form info."""
    # When
    response = client_query(
        """
        mutation {
          createFoodProduct(
            input: {
              energy: 100,
              proteinG: 100,
              fatG: 100,
              name: "retest",
              nutritionalInfoSize: 100,
              nutritionalInfoUnit: "g",
              weight: 100,
              weightUnit: "g",
              numServings: 1,
              carbsG: 100,
              barcode: "1",
            }
          ) {
            foodProduct {
              id
              name
              barcode
            }
          }
        }
        """,
    )
