"""FoodProduct model module."""

from django.db import models

from .food import Food


class FoodProduct(Food):
    """FoodProduct model class."""

    barcode = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=0,
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        res = f"{self.name} ({self.weight}{self.weight_unit})"

        if self.brand:
            res = f"{self.brand} {res}"

        return res
