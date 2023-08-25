from django import forms
import graphene
from graphene import relay
from graphene_django import DjangoObjectType

from .models.product import FoodProduct
from .types import FoodProductNode

from graphene_django.forms.mutation import DjangoModelFormMutation


class FoodProductForm(forms.ModelForm):
    class Meta:
        model = FoodProduct
        fields = "__all__"


class FoodProductMutation(DjangoModelFormMutation):
    food_product = graphene.Field(FoodProductNode)

    class Meta:
        form_class = FoodProductForm

    def resolve_food_product(self, info, **kwargs):
        return self.foodProduct


class FoodsMutations(graphene.ObjectType):
    food_product = FoodProductMutation.Field()
