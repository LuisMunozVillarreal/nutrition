"""FoodProduct model module."""


from django.db import models

from .food import Food
from .quantity import FoodQuantity


class FoodProduct(Food, FoodQuantity):
    """FoodProduct model class."""

    barcode = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    brand = models.CharField(
        max_length=255,
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"{self.brand} {self.name} ({self.serving_size})"
