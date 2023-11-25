import graphene
import openfoodfacts

from .models.product import FoodProduct
from .types import FoodProductType

OPEN_FOOD_FACTS_API = openfoodfacts.API(version="v2")


class FoodProductStatus(graphene.Enum):
    ALREADY_EXISTS = 1
    NOT_FOUND = 2
    CREATED = 3


class FoodProductMutation(graphene.Mutation):
    class Arguments:
        barcode = graphene.String(required=True)
        brand = graphene.String()
        name = graphene.String()
        url = graphene.String()
        energy = graphene.Decimal()
        weight = graphene.Int()
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
    status = graphene.Field(FoodProductStatus)

    def resolve_food_product(self, info, **kwargs):
        return self.food_product

    def resolve_status(self, info, **kwargs):
        return self.status

    @classmethod
    def mutate(cls, root, info, **kwargs):
        """
        -> if Barcode exists in the DB:
           -> Return data from the DB + info that it exists
        -> elif only barcode is sent:
           -> Search barcode in openfoodfacts
              -> if it exists:
                 -> create product in DB
                 -> return data from the DB
              -> else:
                 -> return with the info and offer
                    to enter the data manually
        -> else:
           -> create product based on the form info
        """
        barcode = kwargs["barcode"]
        qs = FoodProduct.objects.filter(barcode=barcode)
        # import ipdb
        # ipdb.set_trace()
        if qs.exists():
            return FoodProductMutation(
                food_product=qs.first(),
                status=FoodProductStatus.ALREADY_EXISTS,
            )
        elif len(kwargs) == 1:
            result = OPEN_FOOD_FACTS_API.product.get(barcode)
            if result["state"] == 1:
                product = result["product"]
                nutrients = product["nutriments"]
                try:
                    food_product = FoodProduct(
                        barcode=barcode,
                        brand=product["brands"],
                        name=product["product_name"],
                        weight=product["product_quantity"],
                        num_servings=(
                            product["product_quantity"] /
                            product["serving_quantity"]
                        ),
                        energy=nutrients["energy"],
                        protein_g=nutrients["proteins_100g"],
                        fat_g=nutrients["fat_100g"],
                        saturated_fat_g=nutrients["saturated-fat_100g"],
                        carbs_g=nutrients["carbohydrates_100g"],
                        fiber_carbs_g=nutrients["fiber_100g"],
                        sugar_carbs_g=nutrients["sugars_100g"],
                        sodium_mg=nutrients["sodium_100g"] / 1000,
                    )
                except IndexError as exp:
                    pass
                    # TODO
                food_product.save()
                return FoodProductMutation(
                    food_product=food_product,
                    status=FoodProductState.CREATED,
                )
            else:
                return FoodProductMutation(
                    status=FoodProductState.NOT_FOUND,
                )
        else:
            food_product = FoodProduct(**kwargs)
            food_product.save()
            return FoodProductMutation(
                food_product=food_product,
                    status=FoodProductState.CREATED,
            )


class FoodsMutations(graphene.ObjectType):
    create_food_product = FoodProductMutation.Field()
