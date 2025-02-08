"""foods.food factories module."""

from decimal import Decimal

from factory.django import DjangoModelFactory

from apps.foods.models import Food


class FoodFactory(DjangoModelFactory):
    """FoodFactory class."""

    class Meta:
        model = Food

    brand = "Ocado"
    name = "Chicken Breast"
    url = "http://food.link"
    energy_kcal = Decimal("106")
    size = Decimal("320")
    size_unit = "g"
    protein_g = 25
    fat_g = Decimal("0.5")
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = Decimal("0.5")
    trans_fat_g = 0
    carbs_g = Decimal("0.3")
    fibre_carbs_g = 0
    sugar_carbs_g = Decimal("0.1")
    sodium_mg = 0
    potassium_mg = 0
    vitamin_a_perc = 20
    vitamin_c_perc = 0
    calcium_perc = 0
    iron_perc = 0
