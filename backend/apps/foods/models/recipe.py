"""Recipe models module."""

from decimal import Decimal
from typing import Any

from django.db import models

from .food import Food
from .nutrients import NUTRIENT_LIST, Nutrients


class Recipe(Food):
    """Recipe models class."""

    description = models.TextField(
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
        return f"{self.name} ({self.num_servings}s)"


class RecipeIngredient(Nutrients):
    """RecipeIngredient models class."""

    recipe = models.ForeignKey(
        "foods.Recipe",
        on_delete=models.CASCADE,
        related_name="ingredients",
    )

    food = models.ForeignKey(
        "foods.Serving",
        on_delete=models.CASCADE,
        related_name="recipes",
    )

    num_servings = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=1,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return (
            f"{self.recipe.name} - {str(self.food)}"
            f" {self.food.serving_size * self.num_servings} "
            f"({self.food.serving_unit})"
        )

    @property
    def size(self) -> Decimal:
        """Get the size of the serving.

        Returns:
            Decimal: the size of the serving.
        """
        return self.food.size

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        for nutrient in NUTRIENT_LIST:
            value = getattr(self.food, nutrient) or 0
            setattr(self, nutrient, value * self.num_servings)

        super().save(*args, **kwargs)
