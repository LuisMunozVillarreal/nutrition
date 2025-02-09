"""FoodProduct model module."""

from django.db import models

from apps.libs.utils import round_no_trailing_zeros

from .food import Food


class FoodProduct(Food):
    """FoodProduct model class."""

    barcode = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=0,
    )

    notes = models.TextField(
        blank=True,
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        res = (
            f"{self.name} ({round_no_trailing_zeros(self.size)}"
            f"{self.size_unit})"
        )

        if self.brand:
            res = f"{self.brand} {res}"

        return res
