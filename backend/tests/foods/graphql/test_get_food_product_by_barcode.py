"""Tests for get_for_food_product_by_barcode query."""


import json

import pytest
from requests.exceptions import HTTPError

QUERY = """
    {{
      getFoodProductByBarcode(
        barcode: "{}",
      ) {{
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
    }}
"""


def test_barcode_exists_in_db(client_query, db, food_product):
    """Barcode sent exists in DB."""
    # When
    response = client_query(QUERY.format(food_product.barcode))

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    product = content["data"]["getFoodProductByBarcode"]
    assert product == {
        "id": "1",
        "brand": "Ocado",
        "name": "Chicken Breast",
        "url": "http://foodproduct.link",
        "barcode": "012308980493",
        "energy": "106.0",
        "weight": "320.0",
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


@pytest.fixture
def openfoodfacts(mocker):
    """openfoodfacts mock."""
    mock = mocker.patch("apps.foods.queries.OPEN_FOOD_FACTS_API")
    mock.product.get.return_value = {
        "status": 1,
        "product": {
            "brands": "Ocado",
            "product_name": "Chicken Breast",
            "product_quantity": "320",
            "serving_quantity": "160",
            "nutriments": {
                "energy": "106",
                "proteins_100g": "25",
                "fat_100g": "0.5",
                "saturated-fat_100g": "0",
                "carbohydrates_100g": "0.3",
                "fiber_100g": "0",
                "sodium_100g": "0",
                "sugars_100g": "0",
            },
        },
    }
    return mock


def test_barcode_exists_in_openfoodfacts(client_query, db, openfoodfacts):
    """Barcode sent exists in openfoodfacts and not in the local DB."""
    # When
    response = client_query(QUERY.format("00000000"))

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    product = content["data"]["getFoodProductByBarcode"]
    assert product == {
        "id": "1",
        "brand": "Ocado",
        "name": "Chicken Breast",
        "barcode": "00000000",
        "url": "",
        "energy": "106",
        "weight": "320",
        "weightUnit": "G",
        "numServings": "2",
        "proteinG": "25",
        "fatG": "0.5",
        "saturatedFatG": "0",
        "polyunsaturatedFatG": None,
        "monosaturatedFatG": None,
        "transFatG": None,
        "carbsG": "0.3",
        "fiberCarbsG": "0",
        "sugarCarbsG": "0",
        "sodiumMg": "0",
        "potassiumMg": None,
        "vitaminAPerc": None,
        "vitaminCPerc": None,
        "calciumPerc": None,
        "ironPerc": None,
    }


@pytest.fixture
def not_found(mocker, openfoodfacts):
    """Not found response mock."""
    error = HTTPError()
    error.response = mocker.MagicMock()
    error.response.status_code = 404
    openfoodfacts.product.get.side_effect = error
    return openfoodfacts


def test_barcode_not_found(client_query, db, not_found):
    """Barcode not found."""
    # When
    response = client_query(QUERY.format("00000000"))

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    assert content["data"]["getFoodProductByBarcode"] is None


@pytest.fixture
def error403(not_found):
    """Error 403 response mock."""
    not_found.product.get.side_effect.response.status_code = 403
    return not_found


def test_openfoodfacts_error(client_query, db, error403):
    """Openfoodfacts raises error."""
    # When
    response = client_query(QUERY.format("00000000"))

    # Then
    assert b"errors" in response.content
    content = json.loads(response.content)
    assert content["data"]["getFoodProductByBarcode"] is None


@pytest.fixture
def status_not_1(openfoodfacts):
    """Status not 1 response mock."""
    openfoodfacts.product.get.return_value["status"] = 2
    return openfoodfacts


def test_status_not_1(client_query, db, status_not_1):
    """Openfoodfacts returns status not 1."""
    # When
    response = client_query(QUERY.format("00000000"))

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    assert content["data"]["getFoodProductByBarcode"] is None


@pytest.fixture
def no_serving_quantity(openfoodfacts):
    """No serving quantity response mock."""
    del openfoodfacts.product.get.return_value["product"]["serving_quantity"]
    return openfoodfacts


def test_no_serving_quantity(client_query, db, no_serving_quantity):
    """Openfoodfacts doesn't return serving quantity."""
    # When
    response = client_query(QUERY.format("00000000"))

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    product = content["data"]["getFoodProductByBarcode"]
    assert product == {
        "id": "1",
        "brand": "Ocado",
        "name": "Chicken Breast",
        "barcode": "00000000",
        "url": "",
        "energy": "106",
        "weight": "320",
        "weightUnit": "G",
        "numServings": "1",
        "proteinG": "25",
        "fatG": "0.5",
        "saturatedFatG": "0",
        "polyunsaturatedFatG": None,
        "monosaturatedFatG": None,
        "transFatG": None,
        "carbsG": "0.3",
        "fiberCarbsG": "0",
        "sugarCarbsG": "0",
        "sodiumMg": "0",
        "potassiumMg": None,
        "vitaminAPerc": None,
        "vitaminCPerc": None,
        "calciumPerc": None,
        "ironPerc": None,
    }


@pytest.fixture
def no_sodium(openfoodfacts):
    """No sodium response mock."""
    del openfoodfacts.product.get.return_value["product"]["nutriments"][
        "sodium_100g"
    ]
    return openfoodfacts


def test_with_sodium(client_query, db, no_sodium):
    """Openfoodfacts doesn't return sodium quantity."""
    # When
    response = client_query(QUERY.format("00000000"))

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    product = content["data"]["getFoodProductByBarcode"]
    assert product == {
        "id": "1",
        "brand": "Ocado",
        "name": "Chicken Breast",
        "barcode": "00000000",
        "url": "",
        "energy": "106",
        "weight": "320",
        "weightUnit": "G",
        "numServings": "2",
        "proteinG": "25",
        "fatG": "0.5",
        "saturatedFatG": "0",
        "polyunsaturatedFatG": None,
        "monosaturatedFatG": None,
        "transFatG": None,
        "carbsG": "0.3",
        "fiberCarbsG": "0",
        "sugarCarbsG": "0",
        "sodiumMg": None,
        "potassiumMg": None,
        "vitaminAPerc": None,
        "vitaminCPerc": None,
        "calciumPerc": None,
        "ironPerc": None,
    }
