"""foods.recipe factories module."""

from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.foods.models import Recipe, RecipeIngredient

from .serving import ServingFactory


class RecipeFactory(DjangoModelFactory):
    """RecipeFactory class."""

    class Meta:
        model = Recipe

    name = "Cooked Chicken Breast"
    description = "Best recipe"
    url = "http://recipe.link"
    nutrients_from_ingredients = False
    num_servings = 2.0
    energy_kcal = Decimal("1060")
    protein_g = 250
    fat_g = 5
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = 0
    trans_fat_g = 0
    carbs_g = 30
    fibre_carbs_g = 0
    sugar_carbs_g = 0
    sodium_mg = 10
    potassium_mg = 0
    vitamin_a_perc = 0
    vitamin_c_perc = 10
    calcium_perc = 0
    iron_perc = 0


class RecipeIngredientFactory(DjangoModelFactory):
    """RecipeIngredientFactory class."""

    class Meta:
        model = RecipeIngredient

    recipe = SubFactory(RecipeFactory)
    food = SubFactory(ServingFactory)
