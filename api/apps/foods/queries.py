"""food app queries module for graphene."""


from decimal import Decimal

import graphene
import openfoodfacts
from requests.exceptions import HTTPError

from apps.foods.models.product import FoodProduct

from .types import FoodProductType

OPEN_FOOD_FACTS_API = openfoodfacts.API(version="v2")


class FoodProductQuery(graphene.ObjectType):
    """FoodProduct query."""

    get_food_product_by_barcode = graphene.Field(
        FoodProductType,
        barcode=graphene.String(),
    )

    def resolve_get_food_product_by_barcode(
        self, info, barcode
    ) -> FoodProduct | None:
        """Resolve get_food_product_by_barcode.

        Args:
            info ():
            barcode (str): barcode.

        Returns:
            FoodProduct: if there is a food product linked to the barcode.
            None: othewise.

        Raises:
            HTTPError: if openfoodfacts raises anything but 404.
        """
        qs = FoodProduct.objects.filter(barcode=barcode)
        if qs.exists():
            return qs.first()

        try:
            result = OPEN_FOOD_FACTS_API.product.get(barcode)
        except HTTPError as error:
            if error.response.status_code == 404:
                return None
            raise error

        if result["status"] == 1:
            product = result["product"]
            nutrients = product["nutriments"]

            food_product = FoodProduct(
                barcode=barcode,
                brand=product["brands"],
                name=product["product_name"],
                weight=str(product["product_quantity"]),
                energy=str(nutrients["energy"]),
                protein_g=str(nutrients["proteins_100g"]),
                fat_g=str(nutrients["fat_100g"]),
                saturated_fat_g=str(nutrients.get("saturated-fat_100g")),
                carbs_g=str(nutrients.get("carbohydrates_100g")),
                fiber_carbs_g=str(nutrients.get("fiber_100g")),
                sugar_carbs_g=str(nutrients.get("sugars_100g")),
            )

            food_product.num_servings = Decimal("1")
            if "serving_quantity" in product:
                food_product.num_servings = Decimal(
                    product["product_quantity"]
                ) / Decimal(product["serving_quantity"])

            if "sodium_100g" in nutrients:
                food_product.sodium_mg = (
                    Decimal(nutrients["sodium_100g"]) / 1000
                )

            food_product.save()
            return food_product
