"""Open Food Facts client tests."""

from datetime import timedelta
from decimal import Decimal, localcontext

import pytest
import requests
from django.utils import timezone

from apps.foods import open_food_facts
from apps.foods.models import OpenFoodFactsCacheEntry, OpenFoodFactsRateLimit
from apps.foods.open_food_facts import (
    OFF_API_BASE_URL,
    OpenFoodFactsProduct,
    fetch_open_food_facts_product,
    parse_quantity,
)

BARCODE = "3017620422003"
OFF_PRODUCT_PAGE = "https://world.openfoodfacts.org/product/3017620422003"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_off_persistence(db):
    """Start each test with an empty OFF cache and quota window."""
    OpenFoodFactsCacheEntry.objects.all().delete()
    OpenFoodFactsRateLimit.objects.all().delete()


def _off_url(barcode: str = BARCODE) -> str:
    """Return the OFF API URL for a barcode.

    Args:
        barcode: product barcode.

    Returns:
        str: OFF API product URL.
    """
    return f"{OFF_API_BASE_URL}/product/{barcode}"


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
    return {"status": "success", "product": product}


def test_parse_quantity_parses_mass_and_volume_labels():
    """Quantity labels parse into an amount and canonical unit."""
    assert parse_quantity("500 g") == (Decimal("500"), "g")
    assert parse_quantity("1,5 kg") == (Decimal("1.5"), "kg")
    assert parse_quantity(" 250 ml ") == (Decimal("250"), "ml")


@pytest.mark.parametrize("quantity", ["", "4 x 100 g", "1000", "33cl can"])
def test_parse_quantity_rejects_unparseable_labels(quantity):
    """Unparseable quantity labels return None."""
    assert parse_quantity(quantity) is None


@pytest.mark.parametrize(
    ("barcode", "expected"),
    [
        ("96385074", "96385074"),
        ("01234565", "01234565"),
        ("036000291452", "036000291452"),
        ("0036000291452", "036000291452"),
        ("00036000291452", "036000291452"),
        ("3017620422003", "3017620422003"),
        ("03017620422003", "3017620422003"),
        ("10012345000017", "10012345000017"),
    ],
)
def test_normalize_gtin_canonicalizes_valid_product_barcode_lengths(
    barcode, expected
):
    """Valid GTINs use their shortest supported equivalent representation."""
    assert open_food_facts.normalize_gtin(f"  {barcode}\n") == expected


def test_equivalent_gtins_preserves_gtin8_representation():
    """GTIN-8 values stay eight digits and never gain zero prefixes."""
    assert open_food_facts.equivalent_gtins("96385074") == ("96385074",)


def test_equivalent_gtins_returns_empty_for_invalid_barcodes():
    """Invalid values produce no stored representations to match."""
    assert not open_food_facts.equivalent_gtins("not-a-barcode")


@pytest.mark.parametrize(
    "barcode",
    [
        "",
        "   ",
        "https://example.com/qr/3017620422003",
        "30176204 22003",
        "1234567",
        "123456789",
        "036000291453",
        "3017620422004",
        "10012345000018",
    ],
)
def test_fetch_rejects_invalid_gtin_without_off_request(
    requests_mock, barcode
):
    """Invalid scan values never become Open Food Facts requests."""
    assert fetch_open_food_facts_product(barcode) is None
    assert not requests_mock.called


def test_fetch_normalizes_surrounding_gtin_whitespace(requests_mock):
    """Surrounding scan whitespace is removed before the OFF request."""
    requests_mock.get(_off_url(), json=_payload())

    product = fetch_open_food_facts_product(f" \t{BARCODE}\n")

    assert product is not None
    assert product.barcode == BARCODE
    assert requests_mock.last_request is not None
    assert requests_mock.last_request.path.endswith(f"/{BARCODE}")


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
    assert requests_mock.last_request is not None
    assert "product_quantity" in requests_mock.last_request.qs["fields"][0]
    assert (
        "product_quantity_unit" in requests_mock.last_request.qs["fields"][0]
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


@pytest.mark.parametrize(
    ("quantity", "quantity_unit", "expected_size", "expected_unit"),
    [
        (1.25, "kg", Decimal("1250"), "g"),
        (1.25, "l", Decimal("1250"), "ml"),
    ],
)
def test_fetch_normalizes_package_precision_for_food_creation(
    requests_mock,
    quantity,
    quantity_unit,
    expected_size,
    expected_unit,
):
    """Normalized package quantities fit the Food one-decimal size field."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            quantity="unparseable multipack",
            product_quantity=quantity,
            product_quantity_unit=quantity_unit,
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (expected_size, expected_unit)


def test_fetch_uses_normalized_volume_quantity_and_basis(requests_mock):
    """A beverage uses OFF's normalized package volume and a 100 ml basis."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            quantity="33 cl",
            product_quantity=330,
            product_quantity_unit="ml",
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (Decimal("330"), "ml")
    assert (
        product.nutritional_info_size,
        product.nutritional_info_unit,
    ) == (Decimal("100"), "ml")


@pytest.mark.parametrize(
    ("product_quantity", "product_quantity_unit"),
    [
        (330, "unit"),
        (None, "ml"),
        (True, "ml"),
        ({"broken": "value"}, "ml"),
        (0, "ml"),
        ("NaN", "ml"),
    ],
)
def test_fetch_ignores_invalid_normalized_package_quantity(
    requests_mock, product_quantity, product_quantity_unit
):
    """Malformed normalized fields fall back to a usable quantity label."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            quantity="350 g",
            product_quantity=product_quantity,
            product_quantity_unit=product_quantity_unit,
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (Decimal("350"), "g")


def test_fetch_rounds_unconvertible_package_precision(requests_mock):
    """Inexact imperial quantities round to compatible positive precision."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            product_quantity=1.234,
            product_quantity_unit="oz",
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (Decimal("1.2"), "oz")


@pytest.mark.parametrize(
    ("quantity", "product_quantity", "product_quantity_unit"),
    [
        ("unparseable", 0, "g"),
        ("unparseable", -1, "g"),
        ("unparseable", "NaN", "g"),
        ("unparseable", "Infinity", "g"),
        ("unparseable", "-Infinity", "g"),
        ("unparseable", 1_000_000_000, "g"),
        ("unparseable", "1e1000", "oz"),
        ("unparseable", 0.01, "oz"),
        ("1000000000 g", None, None),
        ("0 g", None, None),
    ],
)
def test_fetch_keeps_invalid_or_unrepresentable_package_size_null(
    requests_mock, quantity, product_quantity, product_quantity_unit
):
    """Unusable package numbers cannot escape the Food size field contract."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            quantity=quantity,
            product_quantity=product_quantity,
            product_quantity_unit=product_quantity_unit,
        ),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (None, None)


@pytest.mark.parametrize("quantity", ["4 x 100 g", None, ""])
def test_fetch_keeps_unknown_package_size_null(requests_mock, quantity):
    """Missing and multipack labels stay unknown instead of fabricating 100 g."""
    requests_mock.get(_off_url(), json=_payload(quantity=quantity))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert (product.size, product.size_unit) == (None, None)
    assert (
        product.nutritional_info_size,
        product.nutritional_info_unit,
    ) == (Decimal("100"), "g")


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
    """OFF failure status means the barcode is unknown."""
    requests_mock.get(_off_url(), json={"status": "failure"})

    assert fetch_open_food_facts_product(BARCODE) is None


def test_fetch_non_decimal_nutrient_field_maps_to_none(
    requests_mock, monkeypatch
):
    """A non-decimal destination field keeps the nutrient absent."""
    requests_mock.get(_off_url(), json=_payload())
    original_get_field = open_food_facts.FoodProduct._meta.get_field

    def fake_get_field(name):
        if name == "energy_kcal":
            return original_get_field("barcode")
        return original_get_field(name)

    monkeypatch.setattr(
        "apps.foods.open_food_facts.FoodProduct._meta.get_field",
        fake_get_field,
    )
    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.energy_kcal is None
    assert product.protein_g is not None


def test_fetch_decimal_exception_during_unit_conversion_keeps_size_null(
    requests_mock,
):
    """A failed conversion attempt leaves the package size unknown."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            quantity="unparseable",
            product_quantity=1.5,
            product_quantity_unit="kg",
        ),
    )
    with localcontext() as context:
        context.prec = 200
        context.Emax = 10**9
        oversized = Decimal("1e1000000")

    assert (
        open_food_facts.creation_compatible_package_size(oversized, "oz")
        is None
    )


def test_fetch_non_decimal_size_field_maps_to_none(requests_mock, monkeypatch):
    """A non-decimal size field contract leaves the package size unknown."""
    requests_mock.get(
        _off_url(),
        json=_payload(
            product_quantity=1.5,
            product_quantity_unit="kg",
        ),
    )
    original_get_field = open_food_facts.FoodProduct._meta.get_field

    def fake_get_field(name):
        field = original_get_field(name)
        if name == "size":
            return original_get_field("barcode")
        return field

    monkeypatch.setattr(
        "apps.foods.open_food_facts.FoodProduct._meta.get_field",
        fake_get_field,
    )
    assert (
        open_food_facts.creation_compatible_package_size(Decimal("1500"), "g")
        is None
    )
    assert fetch_open_food_facts_product(BARCODE) is not None


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
    """A success response without a product object is unknown."""
    requests_mock.get(
        _off_url(), json={"status": "success", "product": "broken"}
    )

    assert fetch_open_food_facts_product(BARCODE) is None


def test_fetch_non_dict_nutriments_map_nutrients_to_none(requests_mock):
    """A product without a nutriments object keeps a usable draft."""
    requests_mock.get(_off_url(), json=_payload(nutriments="broken"))

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None

    assert product.name == "Nutella"
    assert product.energy_kcal is None


def test_fetch_serves_positive_results_from_cache(requests_mock):
    """A cached provider product avoids a second OFF request."""
    requests_mock.get(_off_url(), json=_payload())

    first = fetch_open_food_facts_product(BARCODE)
    second = fetch_open_food_facts_product(BARCODE)

    assert first is not None
    assert second is not None
    assert second.name == first.name
    assert requests_mock.call_count == 1
    assert OpenFoodFactsCacheEntry.objects.filter(
        barcode=BARCODE, product__isnull=False
    ).exists()


def test_fetch_serves_negative_results_from_cache(requests_mock):
    """A failed lookup is cached so repeated scans stay local."""
    requests_mock.get(_off_url(), json={"status": "failure"})

    assert fetch_open_food_facts_product(BARCODE) is None
    assert fetch_open_food_facts_product(BARCODE) is None

    assert requests_mock.call_count == 1
    assert OpenFoodFactsCacheEntry.objects.filter(
        barcode=BARCODE, product__isnull=True
    ).exists()


def test_fetch_skips_request_when_cache_is_live(requests_mock):
    """A still-valid cache entry fully bypasses the provider request."""
    requests_mock.get(_off_url(), json=_payload())
    OpenFoodFactsCacheEntry.objects.create(
        barcode=BARCODE,
        product=_payload()["product"],
        expires_at=timezone.now() + timedelta(hours=1),
    )

    product = fetch_open_food_facts_product(BARCODE)

    assert product is not None
    assert requests_mock.call_count == 0


def test_fetch_rate_limit_coordinates_request_slots(requests_mock):
    """Slots persist so replicas share the documented OFF quota."""
    requests_mock.get(_off_url(), json=_payload())
    now = timezone.now().timestamp()
    OpenFoodFactsRateLimit.objects.create(
        key=open_food_facts.OFF_RATE_LIMIT_KEY,
        request_timestamps=[now - 1, now - 2],
    )

    assert fetch_open_food_facts_product(BARCODE) is not None

    limiter = OpenFoodFactsRateLimit.objects.get(
        key=open_food_facts.OFF_RATE_LIMIT_KEY
    )
    assert len(limiter.request_timestamps) == 3


def test_fetch_rejects_request_when_quota_window_is_exhausted(requests_mock):
    """A full rolling window blocks new provider reads."""
    now = timezone.now().timestamp()
    OpenFoodFactsRateLimit.objects.create(
        key=open_food_facts.OFF_RATE_LIMIT_KEY,
        request_timestamps=[now - i for i in range(14)],
    )

    with pytest.raises(
        ValueError, match="Open Food Facts lookup is temporarily unavailable"
    ):
        fetch_open_food_facts_product(BARCODE)

    assert requests_mock.call_count == 0


def test_fetch_expired_slots_reopen_the_quota_window(requests_mock):
    """Slots outside the rolling window no longer count against the quota."""
    requests_mock.get(_off_url(), json=_payload())
    OpenFoodFactsRateLimit.objects.create(
        key=open_food_facts.OFF_RATE_LIMIT_KEY,
        request_timestamps=[timezone.now().timestamp() - 120],
    )

    assert fetch_open_food_facts_product(BARCODE) is not None

    limiter = OpenFoodFactsRateLimit.objects.get(
        key=open_food_facts.OFF_RATE_LIMIT_KEY
    )
    assert len(limiter.request_timestamps) == 1
