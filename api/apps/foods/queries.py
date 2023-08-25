import graphene
from graphene import relay


from .types import FoodProductNode


class FoodsQueries(graphene.ObjectType):
    food_product = graphene.Field(FoodProductNode)
