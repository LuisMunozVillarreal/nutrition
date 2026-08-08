"""Open Food Facts client tests."""

from decimal import Decimal

import pytest
import requests

from apps.foods.open_food_facts import (
    OFF_API_BASE_URL,
    OpenFoodFactsProduct,
    fetch_open_food_facts_product,
    parse_quantity,
)

BARCODE = "3017620422003"
OFF_PRODUCT_PAGE = "https://world.openfoodfacts.org/product/3017620422003"


def _off_url(barcode: str = BARCODE) -> str:
    """Return the OFF API URL for a barcode.

    Args:
        barcode: product barcode.

    Returns:
        str: OFF API product URL.
    """
    return f"{OFF_API_BASE_URL}/product/{barcode}.json"


def _payload(**product_overrides) -> dict:
    """Return a complete OFF payload with the given product overrides.

    Args:
        product_overrides: fields to override on the default product.

    Returns:
        dict: OFF API payload.
    """
    product = {
        "product_name": "Nutella",
        "brands": "Nutella, Ferrero",
        "quantity": "350 g",
        "url": OFF_PRODUCT_PAGE,
        "nutriments": {
            "energy-kcal_100g": 539,
            "proteins_100g": 6.3,
            "fat_100g": 30.9,
            "carbohydrates_100g": 57.5,
            "saturated-fat_100g": 10.6,
            "sugars_100g": 56.3,
            "fiber_100g": 3.7,
            "salt_100g": 0.107,
        },
    }
    product.update(product_overrides)
    return {"status": 1, "product": product}


def test_parse_quantity_parses_mass_and_volume_labels():
    """Quantity labels parse into an amount and canonical unit."""
    assert parse_quantity("500 g") == (Decimal("500"), "g")
    assert parse_quantity("1,5 kg") == (Decimal("1.5"), "kg")
    assert parse_quantity(" 250 ml ") == (Decimal("250"), "ml")


@pytest.mark.parametrize("quantity", ["", "4 x 100 g", "1000", "33cl can"])
def test_parse_quantity_rejects_unparseable_labels(quantity):
    """Unparseable quantity labels return None."""
    assert parse_quantity(quantity) is None


def test_fetch_maps_complete_product(requests_mock):
    """A complete OFF product maps to a full draft."""
    requests_mock.get(_off_url(), json=_payload())

    product = fetch_open_food_facts_product(BARCODE)

    assert product == OpenFoodFactsProduct(
        barcode=BARCODE,
        brand="Nutella",
        name="Nutella",
        url=OFF_PRODUCT_PAGE,
        size=Decimal("350"),
        size_unit="g",
        num_servings=Decimal("1"),
        nutritional_info_size=Decimal("100"),
        nutritional_info_unit="g",
        energy_kcal=Decimal("539"),
        protein_g=Decimal("6.3"),
        fat_g=Decimal("30.9"),
        carbs_g=Decimal("57.5"),
        saturated_fat_g=Decimal("10.6"),
        sugars_g=Decimal("56.3"),
        fibre_g=Decimal("3.7"),
        salt_g=Decimal("0.11"),
    )


def test_fetch_rounds_nutrients_and_keeps_first_brand(requests_mock):
    """Nutrients round to two decimals and only the first brand is kept."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            brands="Brand A, Brand B",
            nutriments={
                "energy-kcal_100g": 10.567,
                "proteins_100g": 0.004,
            },
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.brand == "Brand A"
    assert product.energy_kcal == Decimal("10.57")
    assert product.protein_g == Decimal("0")
    assert product.fat_g is None


def test_fetch_ignores_non_numeric_nutrient_markers(requests_mock):
    """Non-numeric OFF markers such as "~" map to None."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            nutriments={
                "energy-kcal_100g": "~",
                "proteins_100g": "<0.5",
                "fat_100g": 12.34,
            }
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.energy_kcal is None
    assert product.protein_g is None
    assert product.fat_g == Decimal("12.34")


def test_fetch_uses_mass_quantity(requests_mock):
    """A mass quantity label becomes the package size."""
    requests_mock.get(_off_url(), json=_payload(quantity="1.5 kg"))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (Decimal("1.5"), "kg")


@pytest.mark.parametrize("quantity", ["33 cl", "4 x 100 g", None, ""])
def test_fetch_defaults_size_when_quantity_is_not_mass(
    requests_mock, quantity
):
    """Non-mass or unparseable quantities default to 100 g."""
    requests_mock.get(_off_url(), json=_payload(quantity=quantity))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (Decimal("100"), "g")


@pytest.mark.parametrize("brands", [None, "", ", "])
def test_fetch_missing_or_empty_brand_maps_to_none(requests_mock, brands):
    """Missing, blank, and comma-only brand fields map to None."""
    requests_mock.get(_off_url(), json=_payload(brands=brands))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.brand is None


def test_fetch_missing_url_uses_barcode_page_fallback(requests_mock):
    """A product without a URL falls back to the barcode page."""
    requests_mock.get(_off_url(), json=_payload(url=None))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.url == OFF_PRODUCT_PAGE


@pytest.mark.parametrize("name", [None, "", "   "])
def test_fetch_unusable_name_returns_none(requests_mock, name):
    """Products without a usable name are treated as unknown."""
    requests_mock.get(_off_url(), json=_payload(product_name=name))

    assert fetch_open_food_facts_product(BARCODE) is None


def test_fetch_unknown_barcode_returns_none(requests_mock):
    """OFF status 0 means the barcode is unknown."""
    requests_mock.get(_off_url(), json={"status": 0})

    assert fetch_open_food_facts_product(BARCODE) is None


def test_fetch_http_404_returns_none(requests_mock):
    """OFF HTTP 404 is treated as an unknown barcode."""
    requests_mock.get(_off_url(), status_code=404)

    assert fetch_open_food_facts_product(BARCODE) is None


@pytest.mark.parametrize("status_code", [500, 503])
def test_fetch_http_errors_raise(requests_mock, status_code):
    """OFF HTTP errors other than 404 surface as lookup failures."""
    requests_mock.get(_off_url(), status_code=status_code)

    with pytest.raises(ValueError, match="Open Food Facts lookup failed"):
        fetch_open_food_facts_product(BARCODE)


def test_fetch_network_errors_raise(requests_mock):
    """OFF connectivity errors surface as lookup failures."""
    requests_mock.get(_off_url(), exc=requests.exceptions.ConnectionError)

    with pytest.raises(ValueError, match="Open Food Facts lookup failed"):
        fetch_open_food_facts_product(BARCODE)


def test_fetch_invalid_json_raises(requests_mock):
    """Malformed OFF responses surface as lookup failures."""
    requests_mock.get(_off_url(), text="not json")

    with pytest.raises(ValueError, match="Open Food Facts lookup failed"):
        fetch_open_food_facts_product(BARCODE)


def test_fetch_non_dict_payload_raises(requests_mock):
    """Non-object OFF responses surface as lookup failures."""
    requests_mock.get(_off_url(), json=[])

    with pytest.raises(ValueError, match="Open Food Facts lookup failed"):
        fetch_open_food_facts_product(BARCODE)


def test_fetch_non_dict_product_returns_none(requests_mock):
    """A status-1 response without a product object is unknown."""
    requests_mock.get(_off_url(), json={"status": 1, "product": "broken"})

    assert fetch_open_food_facts_product(BARCODE) is None


def test_fetch_non_dict_nutriments_map_nutrients_to_none(requests_mock):
    """A product without a nutriments object keeps a usable draft."""
    requests_mock.get(_off_url(), json=_payload(nutriments="broken"))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.name == "Nutella"
    assert product.energy_kcal is None
