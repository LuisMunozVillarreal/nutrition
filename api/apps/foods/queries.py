from apps.foods.models.product import FoodProduct
import graphene
from graphene import relay


from .types import FoodProductNode


class FoodsQueries(graphene.ObjectType):
    food_product = graphene.List(FoodProductNode)
    food_product_search = graphene.List(
        FoodProductNode, barcode=graphene.String(),
    )

    def resolve_food_product(self, info):
        return FoodProduct.objects.all()

    def resolve_food_product_search(self, info, barcode):
        return FoodProduct.objects.filter(barcode=barcode)
