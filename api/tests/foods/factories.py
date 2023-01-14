"""foods app factories module."""


from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.foods.models import Food, Recipe, RecipeIngredient


class FoodFactory(DjangoModelFactory):
    """FoddFactory class."""

    class Meta:
        model = Food

    brand = "Ocado"
    name = "Chicken Breast"
    serving_size = Decimal(100)
    serving_unit = "g"
    calories = 106
    protein_g = 25
    fat_g = Decimal(0.5)
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = 0
    trans_fat_g = 0
    carbs_g = Decimal(0.3)
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
    number_of_servings = 3
    link = "http://recipe.link"
    nutrients_from_ingredients = False
    calories = 1060
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
    food = SubFactory(FoodFactory)
    serving_size = Decimal(100)
    serving_unit = "g"
