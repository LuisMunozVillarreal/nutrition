"""food.signal.handlers module."""

# flake8: noqa: F401
from .cupboard import calculate_consumption_from_cooked_recipes
from .product import add_default_servings
from .recipe_nutrients import (
    calculate_recipe_nutrients,
    decrease_recipe_nutrients,
    increase_recipe_nutrients,
)
from .recipe_servings import (
    add_recipe_serving,
    update_recipe_serving_nutrients,
)
