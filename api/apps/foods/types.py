import graphene
from graphene_django import DjangoObjectType

from .models.product import FoodProduct


class FoodProductType(DjangoObjectType):
    class Meta:
        model = FoodProduct
        fields = "__all__"
