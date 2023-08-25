"""Tests for the Food Product mutation create_food_product."""


import json


def test_create_product_from_form(db, client_query):
    """Create food product from the form info."""
    # When
    response = client_query(
        """
        mutation {
          createFoodProduct(
            energy: 100,
            proteinG: 100,
            fatG: 100,
            name: "retest",
            weight: 100,
            weightUnit: "g",
            numServings: 1,
            carbsG: 100,
            barcode: "1",
          ) {
            foodProduct {
              id
            }
          }
        }
        """,
    )

    # Then
    assert b"errors" not in response.content
    content = json.loads(response.content)
    assert content["data"]["createFoodProduct"]["foodProduct"]["id"] == "1"
