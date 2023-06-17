"""FoodProduct model module."""


from django.db import models

from .food import Food


class FoodProduct(Food):
    """FoodProduct model class."""

    barcode = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        res = f"{self.name} ({self.serving_size} {self.serving_unit})"

        if self.brand:
            res = f"{self.brand} {res}"

        return res
