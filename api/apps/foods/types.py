import graphene
from graphene import relay
from graphene_django import DjangoObjectType

from .models.product import FoodProduct


class FoodProductNode(DjangoObjectType):
    class Meta:
        model = FoodProduct
        interfaces = (relay.Node,)
