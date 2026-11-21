"""Regression tests for conservative OFF catalog reconciliation."""

from decimal import Decimal

import pytest
from django.db.models import QuerySet

from apps.foods.models import FoodProduct, Serving
from apps.foods.off_reconciliation import reconcile_off_product
from apps.foods.open_food_facts import _map_product
from config.schema import schema
from tests.foods.test_product_barcode_schema import (
    BARCODE,
    _create_user,
    _lookup_query,
    _off_payload,
    _off_url,
)


def _product(**changes):
    """Create a catalog product matching the OFF fixture."""
    values = {
        "name": "Nutella",
        "brand": "Ferrero",
        "barcode": None,
        "size": Decimal("350"),
        "size_unit": "g",
        "energy_kcal": Decimal("539"),
        "protein_g": Decimal("6.3"),
        "fat_g": Decimal("30.9"),
        "carbs_g": Decimal("57.5"),
        "salt_g": Decimal("0.11"),
        "notes": "Curated notes",
        "url": "https://example.com/curated",
    }
    values.update(changes)
    return FoodProduct.objects.create(**values)


def _lookup(mocker, requests_mock, *, staff=True, payload=None):
    """Run the public lookup against a mocked provider response."""
    user = _create_user("reconcile@example.com", is_staff=staff)
    context = mocker.Mock()
    context.request.user = user
    requests_mock.get(_off_url(BARCODE), json=payload or _off_payload())
    result = schema.execute_sync(
        _lookup_query(
            "product { id barcode name servings { id } } "
            "openFoodFacts { barcode name }"
        ),
        context_value=context,
    )
    assert result.errors is None
    return result.data["foodProductByBarcode"]


@pytest.mark.django_db
@pytest.mark.parametrize("missing_barcode", [None, "", "0"])
def test_lookup_fills_only_missing_barcode(
    mocker, requests_mock, missing_barcode
):
    """Reuse the exact catalog match without changing curated data."""
    product = _product(barcode=missing_barcode)
    before = FoodProduct.objects.values().get(pk=product.pk)
    servings = list(Serving.objects.filter(food=product).values())

    result = _lookup(mocker, requests_mock)

    assert result["product"] is not None
    assert result["product"]["id"] == str(product.pk)
    assert result["product"]["barcode"] == BARCODE
    assert result["openFoodFacts"] is None
    after = FoodProduct.objects.values().get(pk=product.pk)
    assert after == {**before, "barcode": BARCODE}
    assert list(Serving.objects.filter(food=product).values()) == servings
    assert FoodProduct.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Nutella white"},
        {"brand": "Other"},
        {"brand": None},
        {"size": Decimal("750")},
        {"size_unit": "ml", "nutritional_info_unit": "ml"},
        {"size": Decimal("0.35"), "size_unit": "kg"},
        {"barcode": "036000291452"},
        {"barcode": "invalid-but-established"},
        {"nutritional_info_size": Decimal("50")},
        {"nutritional_info_unit": "kg"},
        {"energy_kcal": Decimal("540")},
        {"protein_g": Decimal("7")},
        {"fat_g": Decimal("31")},
        {"carbs_g": Decimal("58")},
    ],
)
def test_nonmatching_product_is_unchanged(mocker, requests_mock, changes):
    """Similar names, brands, variants and unit mismatches stay drafts."""
    product = _product(**changes)
    before = FoodProduct.objects.values().get(pk=product.pk)

    result = _lookup(mocker, requests_mock)

    assert result["product"] is None
    assert result["openFoodFacts"]["barcode"] == BARCODE
    assert FoodProduct.objects.values().get(pk=product.pk) == before
    assert FoodProduct.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("other_barcode", [None, "036000291452"])
def test_ambiguous_matches_stay_drafts(mocker, requests_mock, other_barcode):
    """Never choose one matching package from multiple catalog candidates."""
    first = _product()
    second = _product(barcode=other_barcode)

    result = _lookup(mocker, requests_mock)

    assert result["product"] is None
    assert result["openFoodFacts"] is not None
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.barcode is None
    assert second.barcode == other_barcode
    assert FoodProduct.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"brands": ""},
        {"quantity": "unknown"},
        {"nutriments": {}},
    ],
)
def test_incomplete_off_identity_stays_draft(mocker, requests_mock, changes):
    """Missing identity or primary nutrition evidence never fills a barcode."""
    product = _product()
    payload = _off_payload()
    payload["product"].update(changes)

    result = _lookup(mocker, requests_mock, payload=payload)

    assert result["product"] is None
    assert result["openFoodFacts"] is not None
    product.refresh_from_db()
    assert product.barcode is None


@pytest.mark.django_db
def test_nonstaff_reuses_product_without_catalog_write(mocker, requests_mock):
    """Authenticated readers can reuse shared foods but cannot amend them."""
    product = _product()
    before = FoodProduct.objects.values().get(pk=product.pk)

    result = _lookup(mocker, requests_mock, staff=False)

    assert result["product"]["id"] == str(product.pk)
    assert result["openFoodFacts"] is None
    assert FoodProduct.objects.values().get(pk=product.pk) == before


@pytest.mark.django_db
def test_case_only_differences_match_without_rewriting(mocker, requests_mock):
    """Case-insensitive whole names and brands retain their curated spelling."""
    product = _product(name="NUTELLA", brand="ferrero")

    result = _lookup(mocker, requests_mock)

    assert result["product"]["id"] == str(product.pk)
    assert result["product"]["name"] == "NUTELLA"
    product.refresh_from_db()
    assert product.brand == "ferrero"


@pytest.mark.django_db
def test_rechecks_barcode_after_off_response(mocker, requests_mock):
    """A product created during network I/O wins over the provider draft."""
    product = _product()

    def response(_request, _context):
        FoodProduct.objects.filter(pk=product.pk).update(barcode=BARCODE)
        return _off_payload()

    result = _lookup(mocker, requests_mock, payload=response)

    assert result["product"]["id"] == str(product.pk)
    assert result["openFoodFacts"] is None
    assert FoodProduct.objects.count() == 1


@pytest.mark.django_db
def test_barcode_claim_during_candidate_read_is_reused(mocker):
    """Recheck barcode identity after waiting for candidate locks."""
    product = _product()
    draft = _map_product(_off_payload()["product"], BARCODE)
    original = QuerySet.select_for_update

    def claim(queryset, *args, **kwargs):
        FoodProduct.objects.filter(pk=product.pk).update(barcode=BARCODE)
        return original(queryset, *args, **kwargs)

    mocker.patch.object(QuerySet, "select_for_update", claim)

    result = reconcile_off_product(draft, may_update=True)

    assert result.pk == product.pk
    assert result.barcode == BARCODE
    assert FoodProduct.objects.count() == 1


@pytest.mark.django_db
def test_conditional_update_preserves_competing_barcode(mocker):
    """Even without row locks, a different barcode is never overwritten."""
    product = _product()
    draft = _map_product(_off_payload()["product"], BARCODE)
    original = QuerySet.update

    def claim(queryset, **kwargs):
        original(
            FoodProduct.objects.filter(pk=product.pk), barcode="036000291452"
        )
        return original(queryset, **kwargs)

    mocker.patch.object(QuerySet, "update", claim)

    assert reconcile_off_product(draft, may_update=True) is None
    product.refresh_from_db()
    assert product.barcode == "036000291452"
    assert FoodProduct.objects.count() == 1


@pytest.mark.django_db
def test_reconciliation_failure_rolls_back_barcode(mocker):
    """A failure after the write leaves the original catalog row untouched."""
    product = _product()
    before = FoodProduct.objects.values().get(pk=product.pk)
    draft = _map_product(_off_payload()["product"], BARCODE)
    mocker.patch.object(
        FoodProduct, "refresh_from_db", side_effect=RuntimeError("injected")
    )

    with pytest.raises(RuntimeError, match="injected"):
        reconcile_off_product(draft, may_update=True)

    assert FoodProduct.objects.values().get(pk=product.pk) == before
