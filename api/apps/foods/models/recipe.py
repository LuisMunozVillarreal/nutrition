"""Recipe models module."""


from django.db import models

from .nutrients import Nutrients
from .proportion import FoodProportion


class Recipe(Nutrients):
    """Recipe models class."""

    name = models.CharField(
        max_length=255,
    )

    description = models.TextField(
        blank=True,
    )

    number_of_servings = models.PositiveIntegerField()

    link = models.URLField(
        blank=True,
    )

    nutrients_from_ingredients = models.BooleanField(
        default=False,
        verbose_name="Calculate nutrients from ingredients",
    )

    @property
    def num_ingredients(self) -> int:
        """Get number of ingredients.

        Returns:
            str: number of ingredients.
        """
        return self.ingredients.count()

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return self.name


class RecipeIngredient(FoodProportion):
    """RecipeIngredient models class."""

    recipe = models.ForeignKey(
        "foods.Recipe",
        on_delete=models.CASCADE,
        related_name="ingredients",
    )

    food = models.ForeignKey(
        "foods.Food",
        on_delete=models.CASCADE,
        related_name="recipes",
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return (
            f"{self.recipe.name} - {str(self.food)}"
            f" {self.serving_size} ({self.serving_unit})"
        )
