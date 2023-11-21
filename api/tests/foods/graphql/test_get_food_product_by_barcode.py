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
        """.format(food_product.barcode),
    )

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    product = content["data"]["getFoodProductByBarcode"]
    assert len(product) == 1
    assert product[0] == {
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
