from apps.foods.models.product import FoodProduct
import graphene


from .types import FoodProductType


class FoodsQueries(graphene.ObjectType):
    get_food_product_by_barcode = graphene.List(
        FoodProductType,
        barcode=graphene.String(),
    )

    def resolve_get_food_product_by_barcode(self, info, barcode):
        print(barcode)
        return FoodProduct.objects.filter(barcode=barcode)
