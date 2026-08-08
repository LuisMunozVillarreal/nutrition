"""Open Food Facts barcode lookup client module."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings

OFF_API_BASE_URL = "https://world.openfoodfacts.org/api/v2"
OFF_PRODUCT_PAGE_URL = "https://world.openfoodfacts.org/product/{barcode}"
OFF_REQUEST_TIMEOUT_SECONDS = 10

MASS_UNITS = frozenset({"g", "kg", "mg", "oz", "lb"})
VOLUME_UNITS = frozenset({"ml", "cl", "l", "c", "floz", "tbsp", "tsp", "pt"})
CANONICAL_UNITS = MASS_UNITS | VOLUME_UNITS

QUANTITY_PATTERN = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*"
    r"(g|kg|mg|oz|lb|ml|cl|l|c|floz|tbsp|tsp|pt)\s*$",
    re.IGNORECASE,
)

#: OFF v2 per-100g nutriment keys, mapped to draft attribute names.
NUTRIMENT_KEYS = {
    "energy_kcal": "energy-kcal",
    "protein_g": "proteins",
    "fat_g": "fat",
    "carbs_g": "carbohydrates",
    "saturated_fat_g": "saturated-fat",
    "sugars_g": "sugars",
    "fibre_g": "fiber",
    "salt_g": "salt",
}


@dataclass(frozen=True)
class OpenFoodFactsProduct:
    """Nutrition draft mapped from an Open Food Facts product."""

    # pylint: disable=too-many-instance-attributes
    barcode: str
    brand: str | None
    name: str
    url: str
    size: Decimal
    size_unit: str
    num_servings: Decimal
    nutritional_info_size: Decimal
    nutritional_info_unit: str
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None
    saturated_fat_g: Decimal | None
    sugars_g: Decimal | None
    fibre_g: Decimal | None
    salt_g: Decimal | None


def parse_quantity(quantity: str) -> tuple[Decimal, str] | None:
    """Parse an OFF quantity label into an amount and canonical unit.

    Args:
        quantity: Product quantity label, e.g. "500 g" or "33 cl".

    Returns:
        tuple[Decimal, str] | None: amount and canonical unit, or None when
        the label does not match a single canonical quantity.
    """
    match = QUANTITY_PATTERN.match(quantity)
    if match is None:
        return None
    amount = Decimal(match.group(1).replace(",", "."))
    return amount, match.group(2).lower()


def fetch_open_food_facts_product(
    barcode: str,
) -> OpenFoodFactsProduct | None:
    """Fetch and map an Open Food Facts product for a barcode.

    The draft always uses the per-100g nutrition basis because Open Food
    Facts exposes per-100g values for mass and volume products alike. The
    package size is only carried over when its unit is mass-compatible;
    otherwise the draft defaults to 100 g for the user to adjust.

    Args:
        barcode: The scanned product barcode.

    Returns:
        OpenFoodFactsProduct | None: the mapped product draft, or None when
        the barcode is unknown or the product has no usable name.

    Raises:
        ValueError: When Open Food Facts cannot be reached.
    """
    try:
        response = requests.get(
            f"{OFF_API_BASE_URL}/product/{barcode}.json",
            headers={"User-Agent": settings.OPEN_FOOD_FACTS_USER_AGENT},
            timeout=OFF_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise ValueError("Open Food Facts lookup failed") from exc
    except requests.exceptions.RequestException as exc:
        raise ValueError("Open Food Facts lookup failed") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Open Food Facts lookup failed") from exc

    if not isinstance(payload, dict):
        raise ValueError("Open Food Facts lookup failed")

    if payload.get("status") != 1:
        return None

    product = payload.get("product")
    if not isinstance(product, dict):
        return None

    name = product.get("product_name")
    if not isinstance(name, str) or not name.strip():
        return None

    size, size_unit = _package_size(product)
    nutriments = product.get("nutriments")
    nutriment_values = nutriments if isinstance(nutriments, dict) else {}

    return OpenFoodFactsProduct(
        barcode=barcode,
        brand=_brand(product.get("brands")),
        name=name.strip(),
        url=_product_url(product, barcode),
        size=size,
        size_unit=size_unit,
        num_servings=Decimal("1"),
        nutritional_info_size=Decimal("100"),
        nutritional_info_unit="g",
        energy_kcal=_nutriment_value(nutriment_values, "energy_kcal"),
        protein_g=_nutriment_value(nutriment_values, "protein_g"),
        fat_g=_nutriment_value(nutriment_values, "fat_g"),
        carbs_g=_nutriment_value(nutriment_values, "carbs_g"),
        saturated_fat_g=_nutriment_value(nutriment_values, "saturated_fat_g"),
        sugars_g=_nutriment_value(nutriment_values, "sugars_g"),
        fibre_g=_nutriment_value(nutriment_values, "fibre_g"),
        salt_g=_nutriment_value(nutriment_values, "salt_g"),
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    """Return a rounded decimal value, or None when it is unavailable.

    Open Food Facts occasionally publishes non-numeric markers such as "~"
    or "<0.5"; those map to None so the draft stays valid for the form.

    Args:
        value: Raw nutriment value from the Open Food Facts response.

    Returns:
        Decimal | None: value rounded to two decimals, or None.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation:
        return None


def _nutriment_value(
    nutriments: dict[str, Any], attribute: str
) -> Decimal | None:
    """Return the rounded per-100g value for a draft nutrient attribute.

    Args:
        nutriments: OFF nutriments mapping.
        attribute: Draft attribute name from NUTRIMENT_KEYS.

    Returns:
        Decimal | None: the rounded per-100g value, or None.
    """
    key = f"{NUTRIMENT_KEYS[attribute]}_100g"
    return _decimal_or_none(nutriments.get(key))


def _brand(brands: Any) -> str | None:
    """Return the first OFF brand, or None when there is none.

    Args:
        brands: Raw brands field, often a comma-separated string.

    Returns:
        str | None: the first brand, trimmed, or None.
    """
    if not brands:
        return None
    first = str(brands).split(",", maxsplit=1)[0].strip()
    return first or None


def _product_url(product: dict[str, Any], barcode: str) -> str:
    """Return the OFF product page URL for a product.

    Args:
        product: OFF product mapping.
        barcode: Product barcode used for the fallback page URL.

    Returns:
        str: the product page URL.
    """
    url = product.get("url")
    if isinstance(url, str) and url:
        return url
    return OFF_PRODUCT_PAGE_URL.format(barcode=barcode)


def _package_size(product: dict[str, Any]) -> tuple[Decimal, str]:
    """Return a package size compatible with the mass nutrition basis.

    Args:
        product: OFF product mapping.

    Returns:
        tuple[Decimal, str]: amount and canonical mass unit.
    """
    quantity = product.get("quantity")
    if isinstance(quantity, str):
        parsed = parse_quantity(quantity)
        if parsed is not None and parsed[1] in MASS_UNITS:
            return parsed
    return Decimal("100"), "g"
