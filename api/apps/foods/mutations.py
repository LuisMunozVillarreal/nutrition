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
        return self.food_product

    @classmethod
    def mutate(cls, self, info, input):
        food_product = FoodProduct(**input)
        food_product.save()
        return FoodProductMutation(food_product=food_product)


class FoodsMutations(graphene.ObjectType):
    create_food_product = FoodProductMutation.Field()
