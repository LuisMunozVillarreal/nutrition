"""foods app factories module."""

from datetime import datetime, timezone
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.foods.models import (
    CupboardItem,
    CupboardItemServing,
    Food,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)


class FoodFactory(DjangoModelFactory):
    """FoodFactory class."""

    class Meta:
        model = Food

    brand = "Ocado"
    name = "Chicken Breast"
    url = "http://food.link"
    energy = Decimal("106")
    weight = Decimal("320")
    weight_unit = "g"
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


class ServingFactory(DjangoModelFactory):
    """ServingFactory class."""

    class Meta:
        model = Serving

    food = SubFactory(FoodFactory)


class FoodProductFactory(DjangoModelFactory):
    """FoddProductFactory class."""

    class Meta:
        model = FoodProduct

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


class RecipeFactory(DjangoModelFactory):
    """RecipeFactory class."""

    class Meta:
        model = Recipe

    name = "Cooked Chicken Breast"
    description = "Best recipe"
    url = "http://recipe.link"
    nutrients_from_ingredients = False
    num_servings = 2.0
    energy = Decimal("1060")
    protein_g = 250
    fat_g = 5
    saturated_fat_g = 0
    polyunsaturated_fat_g = 0
    monosaturated_fat_g = 0
    trans_fat_g = 0
    carbs_g = 30
    fibre_carbs_g = 0
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
    food = SubFactory(ServingFactory)


class CupboardItemFactory(DjangoModelFactory):
    """CupboardItemFactory class."""

    class Meta:
        model = CupboardItem

    food = SubFactory(FoodFactory)
    purchased_at = datetime(2020, 12, 21, 0, 0, 0, tzinfo=timezone.utc)


class CupboardItemServingFactory(DjangoModelFactory):
    """CupboardItemServingFactory class."""

    class Meta:
        model = CupboardItemServing

    item = SubFactory(CupboardItemFactory)
    # serving = SubFactory(ServingFactory)
    food = SubFactory(FoodFactory)
