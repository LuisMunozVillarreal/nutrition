"""Open Food Facts barcode lookup client module."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, DecimalException, InvalidOperation
from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.foods.models import FoodProduct

OFF_API_BASE_URL = "https://world.openfoodfacts.org/api/v2"
OFF_PRODUCT_PAGE_URL = "https://world.openfoodfacts.org/product/{barcode}"
OFF_REQUEST_TIMEOUT_SECONDS = 10
OFF_PRODUCT_FIELDS = ",".join(
    (
        "brands",
        "nutriments",
        "product_name",
        "product_quantity",
        "product_quantity_unit",
        "quantity",
        "url",
    )
)

MASS_UNITS = frozenset({"g", "kg", "mg", "oz", "lb"})
VOLUME_UNITS = frozenset({"ml", "cl", "l", "c", "floz", "tbsp", "tsp", "pt"})
CANONICAL_UNITS = MASS_UNITS | VOLUME_UNITS
PACKAGE_UNIT_CONVERSIONS = {
    "kg": ((Decimal("1000"), "g"),),
    "g": ((Decimal("1000"), "mg"),),
    "lb": ((Decimal("16"), "oz"),),
    "oz": (
        (Decimal("28.349523125"), "g"),
        (Decimal("28349.523125"), "mg"),
    ),
    "l": ((Decimal("1000"), "ml"),),
    "cl": ((Decimal("10"), "ml"),),
    "pt": ((Decimal("16"), "floz"),),
    "c": ((Decimal("8"), "floz"),),
    "tbsp": ((Decimal("3"), "tsp"),),
    "floz": ((Decimal("29.573529562499985"), "ml"),),
    "tsp": ((Decimal("4.92892159375"), "ml"),),
}
FOOD_SIZE_QUANTUM = Decimal("0.1")
GTIN_LENGTHS = frozenset({8, 12, 13, 14})

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
NUTRIMENT_MODEL_FIELDS = {
    "sugars_g": "sugar_carbs_g",
    "fibre_g": "fibre_carbs_g",
}


@dataclass(frozen=True)
class OpenFoodFactsProduct:
    """Nutrition draft mapped from an Open Food Facts product."""

    # pylint: disable=too-many-instance-attributes
    barcode: str
    brand: str | None
    name: str
    url: str
    size: Decimal | None
    size_unit: str | None
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


def normalize_gtin(barcode: str) -> str | None:
    """Normalize and validate a product GTIN barcode.

    Only GTIN-8, UPC-A/GTIN-12, EAN-13, and GTIN-14 values with a valid GS1
    check digit are accepted. Surrounding whitespace is removed. Equivalent
    zero-prefixed 13- and 14-digit forms are reduced no further than GTIN-12;
    GTIN-8 values are preserved.

    Args:
        barcode: Raw scanned barcode value.

    Returns:
        str | None: normalized GTIN, or None when it is invalid.
    """
    normalized = barcode.strip()
    if (
        len(normalized) not in GTIN_LENGTHS
        or re.fullmatch(r"[0-9]+", normalized) is None
    ):
        return None

    weighted_sum = sum(
        int(digit) * (3 if position % 2 else 1)
        for position, digit in enumerate(reversed(normalized[:-1]), start=1)
    )
    check_digit = (10 - weighted_sum % 10) % 10
    if check_digit != int(normalized[-1]):
        return None
    while len(normalized) > 12 and normalized.startswith("0"):
        normalized = normalized[1:]
    return normalized


def equivalent_gtins(barcode: str) -> tuple[str, ...]:
    """Return supported stored representations equivalent to a valid GTIN.

    Args:
        barcode: Raw or canonical GTIN value.

    Returns:
        tuple[str, ...]: Canonical form followed by zero-prefixed legacy forms.
    """
    canonical = normalize_gtin(barcode)
    if canonical is None:
        return ()
    if len(canonical) == 8:
        return (canonical,)
    return tuple(
        canonical.zfill(length) for length in range(len(canonical), 15)
    )


def fetch_open_food_facts_product(
    barcode: str,
) -> OpenFoodFactsProduct | None:
    """Fetch and map an Open Food Facts product for a barcode.

    The draft uses a 100 g basis for mass products and a 100 ml basis for
    volume products. Normalized OFF package quantities take precedence over
    display labels and are converted when needed to fit the Food model's
    one-decimal package-size precision.

    Args:
        barcode: The scanned product barcode.

    Returns:
        OpenFoodFactsProduct | None: the mapped product draft, or None when
        the barcode is unknown or the product has no usable name.

    Raises:
        ValueError: When Open Food Facts cannot be reached.
    """
    normalized_barcode = normalize_gtin(barcode)
    if normalized_barcode is None:
        return None
    encoded_barcode = quote(normalized_barcode, safe="")

    try:
        response = requests.get(
            f"{OFF_API_BASE_URL}/product/{encoded_barcode}.json",
            headers={"User-Agent": settings.OPEN_FOOD_FACTS_USER_AGENT},
            params={"fields": OFF_PRODUCT_FIELDS},
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

    nutritional_info_unit = "ml" if size_unit in VOLUME_UNITS else "g"
    return OpenFoodFactsProduct(
        barcode=normalized_barcode,
        brand=_brand(product.get("brands")),
        name=name.strip(),
        url=_product_url(product, normalized_barcode),
        size=size,
        size_unit=size_unit,
        num_servings=Decimal("1"),
        nutritional_info_size=Decimal("100"),
        nutritional_info_unit=nutritional_info_unit,
        energy_kcal=_nutriment_value(nutriment_values, "energy_kcal"),
        protein_g=_nutriment_value(nutriment_values, "protein_g"),
        fat_g=_nutriment_value(nutriment_values, "fat_g"),
        carbs_g=_nutriment_value(nutriment_values, "carbs_g"),
        saturated_fat_g=_nutriment_value(nutriment_values, "saturated_fat_g"),
        sugars_g=_nutriment_value(nutriment_values, "sugars_g"),
        fibre_g=_nutriment_value(nutriment_values, "fibre_g"),
        salt_g=_nutriment_value(nutriment_values, "salt_g"),
    )


def _decimal_or_none(
    value: Any, model_field: models.DecimalField
) -> Decimal | None:
    """Return a rounded decimal value, or None when it is unavailable.

    Open Food Facts occasionally publishes non-numeric markers such as "~"
    or "<0.5"; those map to None so the draft stays valid for the form.

    Args:
        value: Raw nutriment value from the Open Food Facts response.
        model_field: Destination nutrient field contract.

    Returns:
        Decimal | None: value rounded to two decimals, or None.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value))
        if not decimal_value.is_finite() or decimal_value < 0:
            return None
        quantum = Decimal(1).scaleb(-model_field.decimal_places)
        rounded_value = decimal_value.quantize(quantum, rounding=ROUND_HALF_UP)
        return model_field.clean(rounded_value, None)
    except (DecimalException, ValidationError, ValueError):
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
    model_field_name = NUTRIMENT_MODEL_FIELDS.get(attribute, attribute)
    model_field = FoodProduct._meta.get_field(model_field_name)
    if not isinstance(model_field, models.DecimalField):
        return None
    return _decimal_or_none(nutriments.get(key), model_field)


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


def _package_size(
    product: dict[str, Any],
) -> tuple[Decimal | None, str | None]:
    """Return a package size compatible with the Food model.

    Args:
        product: OFF product mapping.

    Returns:
        tuple[Decimal | None, str | None]: creation-compatible package fields,
        or two None values when the quantity is unknown.
    """
    normalized = _normalized_package_size(product)
    if normalized is not None:
        return normalized

    quantity = product.get("quantity")
    if isinstance(quantity, str):
        parsed = parse_quantity(quantity)
        if parsed is not None:
            compatible = _creation_compatible_package_size(*parsed)
            if compatible is not None:
                return compatible
    return None, None


def _normalized_package_size(
    product: dict[str, Any],
) -> tuple[Decimal, str] | None:
    """Return OFF's normalized package quantity when it is usable.

    Args:
        product: OFF product mapping.

    Returns:
        tuple[Decimal, str] | None: normalized amount and canonical unit.
    """
    unit = product.get("product_quantity_unit")
    if not isinstance(unit, str):
        return None
    canonical_unit = unit.strip().lower()
    if canonical_unit not in CANONICAL_UNITS:
        return None

    amount = _positive_decimal(product.get("product_quantity"))
    if amount is None:
        return None
    return _creation_compatible_package_size(amount, canonical_unit)


def _positive_decimal(value: Any) -> Decimal | None:
    """Return a finite positive decimal, or None for an unusable value.

    Args:
        value: Raw OFF numeric value.

    Returns:
        Decimal | None: finite positive value or None.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount


def _creation_compatible_package_size(
    amount: Decimal, unit: str
) -> tuple[Decimal, str] | None:
    """Represent a package quantity with at most one decimal place.

    Exact canonical-unit conversions are preferred. If no exact conversion
    fits the Food model, the original-unit amount is rounded to its supported
    precision instead of returning a draft that creation would reject.

    Args:
        amount: Positive package quantity.
        unit: Canonical package unit.

    Returns:
        tuple[Decimal, str] | None: one-decimal-compatible amount and unit,
        or None when no valid representation fits the Food size field.
    """
    validated_amount = _food_size_or_none(amount)
    if validated_amount is not None:
        return validated_amount, unit

    for factor, converted_unit in PACKAGE_UNIT_CONVERSIONS.get(unit, ()):
        try:
            converted_amount = amount * factor
        except DecimalException:
            continue
        validated_amount = _food_size_or_none(converted_amount)
        if validated_amount is not None:
            return validated_amount, converted_unit

    try:
        rounded_amount = amount.quantize(
            FOOD_SIZE_QUANTUM, rounding=ROUND_HALF_UP
        )
    except DecimalException:
        return None
    validated_amount = _food_size_or_none(rounded_amount)
    if validated_amount is None:
        return None
    return validated_amount, unit


def _food_size_or_none(amount: Decimal) -> Decimal | None:
    """Validate a package amount against the Food size field contract."""
    if not amount.is_finite() or amount <= 0:
        return None
    try:
        quantized = amount.quantize(FOOD_SIZE_QUANTUM)
        if amount != quantized:
            return None
        field = FoodProduct._meta.get_field("size")
        if not isinstance(field, models.DecimalField):
            return None
        return field.clean(quantized, None)
    except (DecimalException, ValidationError):
        return None
