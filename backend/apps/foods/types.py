"""Graphene Food types."""


from graphene_django import DjangoObjectType

from .models.product import FoodProduct


class FoodProductType(DjangoObjectType):
    """FoodProduct type for graphene."""

    class Meta:
        model = FoodProduct
        fields = "__all__"
