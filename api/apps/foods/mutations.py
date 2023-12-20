"""food app mutations module for graphene."""


import graphene

from .models.product import FoodProduct
from .types import FoodProductType


class FoodProductMutation(graphene.Mutation):
    """FoodProduct mutation."""

    class Arguments:
        barcode = graphene.String(required=True)
        brand = graphene.String()
        name = graphene.String()
        url = graphene.String()
        energy = graphene.Decimal()
        weight = graphene.Decimal()
        weight_unit = graphene.String()
        num_servings = graphene.Decimal()
        protein_g = graphene.Decimal()
        fat_g = graphene.Decimal()
        saturated_fat_g = graphene.Decimal()
        polyunsaturated_fat_g = graphene.Decimal()
        monosaturated_fat_g = graphene.Decimal()
        trans_fat_g = graphene.Decimal()
        carbs_g = graphene.Decimal()
        fiber_carbs_g = graphene.Decimal()
        sugar_carbs_g = graphene.Decimal()
        sodium_mg = graphene.Decimal()
        potassium_mg = graphene.Decimal()
        vitamin_a_perc = graphene.Int()
        vitamin_c_perc = graphene.Int()
        calcium_perc = graphene.Int()
        iron_perc = graphene.Int()

    food_product = graphene.Field(FoodProductType)

    def resolve_food_product(self, info, **kwargs) -> FoodProduct:
        """Resolve food_product.

        Args:
            info ():
            kwargs (Dict[]): keyword arguments.

        Returns:
            FoodProduct: created instance.
        """
        return self.food_product

    @classmethod
    def mutate(cls, root, info, **kwargs):
        """Mutate.

        Args:
            root ():
            info ():
            kwargs (Dict[]): keyword arguments.

        Returns:
            FoodProductMutation:
        """
        food_product = FoodProduct(**kwargs)
        food_product.save()
        return FoodProductMutation(food_product=food_product)


class FoodsMutations(graphene.ObjectType):
    """Foods app mutations."""

    create_food_product = FoodProductMutation.Field()
