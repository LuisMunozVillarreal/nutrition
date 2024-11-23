"""foods.product factories module."""

from decimal import Decimal

from factory import post_generation
from factory.django import DjangoModelFactory

from apps.foods.models import FoodProduct


class FoodProductFactory(DjangoModelFactory):
    """FoddProductFactory class."""

    class Meta:
        model = FoodProduct
        skip_postgeneration_save = True

    brand = "Ocado"
    name = "Chicken Breast"
    url = "http://foodproduct.link"
    barcode = "012308980493"
    energy = Decimal("106")
    weight = Decimal("320")
    weight_unit = "g"
    num_servings = 2
    protein_g = 25
    fat_g = Decimal("0.5")
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = 0
    trans_fat_g = 0
    carbs_g = Decimal("0.3")
    fibre_carbs_g = 0
    sugar_carbs_g = 0
    sodium_mg = 0
    potassium_mg = 0
    vitamin_a_perc = 0
    vitamin_c_perc = 0
    calcium_perc = 0
    iron_perc = 0

    @post_generation
    def tags(obj, create, extracted, **kwargs):
        """Add tags to the factory."""
        if not create:
            return

        obj.tags.add("chicken", "breast")
