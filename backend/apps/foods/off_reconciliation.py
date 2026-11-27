"""Conservatively reconcile OFF drafts with the shared food catalog."""

from django.db import transaction
from django.db.models import Q

from apps.foods.models import FoodProduct
from apps.foods.open_food_facts import OpenFoodFactsProduct, equivalent_gtins

# The model historically used 0 as its default for an unknown barcode.
MISSING_BARCODES = (None, "", "0")
PRIMARY_NUTRIENTS = ("energy_kcal", "protein_g", "fat_g", "carbs_g")


@transaction.atomic
def reconcile_off_product(
    draft: OpenFoodFactsProduct, *, may_update: bool
) -> FoodProduct | None:
    """Return one exact catalog match and optionally fill its absent barcode.

    Match the entire name and brand, package and nutrition basis, and all
    four primary nutrients. Do not infer equivalent units or fuzzy names.
    Ambiguous packages and established different barcodes require review.
    Only staff callers may amend this shared catalog. No products are created.

    Args:
        draft: Mapped OFF response for the scanned barcode.
        may_update: Whether the authenticated caller has catalog write access.

    Returns:
        FoodProduct | None: The existing product, or None for user review.
    """
    barcode_matches = FoodProduct.objects.filter(
        barcode__in=equivalent_gtins(draft.barcode)
    )
    # A local row may have appeared while the provider request was in flight.
    product = barcode_matches.first()
    if product is not None:
        return product
    if not draft.brand or draft.size is None or draft.size_unit is None:
        return None
    candidates = list(
        FoodProduct.objects.select_for_update()
        .filter(
            name__iexact=draft.name,
            brand__iexact=draft.brand,
            size=draft.size,
            size_unit=draft.size_unit,
        )
        .order_by("pk")[:2]
    )
    # Lock the inherited food/nutrient rows too: their identity fields must
    # remain stable until the barcode-only update has committed.
    product = barcode_matches.first()
    if product is not None:
        return product
    if len(candidates) != 1:
        return None
    product = candidates[0]
    if (
        product.barcode not in MISSING_BARCODES
        or product.nutritional_info_size != draft.nutritional_info_size
        or product.nutritional_info_unit != draft.nutritional_info_unit
        or any(
            getattr(draft, field) is None
            or getattr(product, field) != getattr(draft, field)
            for field in PRIMARY_NUTRIENTS
        )
    ):
        return None
    if may_update:
        # Bypass save hooks so curated nutrients, timestamps, and servings
        # remain untouched. The condition also protects non-locking backends.
        FoodProduct.objects.filter(pk=product.pk).filter(
            Q(barcode__isnull=True) | Q(barcode__in=("", "0"))
        ).update(barcode=draft.barcode)
        product.refresh_from_db()
        if product.barcode != draft.barcode:
            product = None
    return product
