"""foods app factories module."""


from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.foods.models import FoodProduct, Recipe, RecipeIngredient


class FoodProductFactory(DjangoModelFactory):
    """FoddFactory class."""

    class Meta:
        model = FoodProduct

    brand = "Ocado"
    name = "Chicken Breast"
    serving_size = Decimal("100")
    serving_unit = "g"
    url = "http://food.link"
    calories = Decimal("106")
    protein_g = 25
    fat_g = Decimal("0.5")
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = 0
    trans_fat_g = 0
    carbs_g = Decimal("0.3")
    fiber_carbs_g = 0
    sugar_carbs_g = 0
    sodium_mg = 0
    potassium_mg = 0
    vitamin_a_perc = 0
    vitamin_c_perc = 0
    calcium_perc = 0
    iron_perc = 0


class RecipeFactory(DjangoModelFactory):
    """RecipeFactory class."""

    class Meta:
        model = Recipe

    name = "Cooked Chicken Breast"
    description = "Best recipe"
    serving_size = 3
    serving_unit = "u"
    url = "http://recipe.link"
    nutrients_from_ingredients = False
    calories = Decimal("1060")
    protein_g = 250
    fat_g = 5
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = 0
    trans_fat_g = 0
    carbs_g = 30
    fiber_carbs_g = 0
    sugar_carbs_g = 0
    sodium_mg = 0
    potassium_mg = 0
    vitamin_a_perc = 0
    vitamin_c_perc = 0
    calcium_perc = 0
    iron_perc = 0


class RecipeIngredientFactory(DjangoModelFactory):
    """RecipeIngredientFactory class."""

    class Meta:
        model = RecipeIngredient

    recipe = SubFactory(RecipeFactory)
    food = SubFactory(FoodProductFactory)
    serving_size = Decimal("100")
    serving_unit = "g"
