"""Food model module."""


from django.db import models

from .quantity import FoodQuantity


class Food(FoodQuantity):
    """Food model class."""

    name = models.CharField(
        max_length=255,
    )

    barcode = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    brand = models.CharField(
        max_length=255,
    )

    calories = models.DecimalField(
        max_digits=10,
        decimal_places=1,
    )

    protein_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
    )

    fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Total Fat (g)",
    )

    carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Total Carbs (g)",
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"{self.brand} {self.name} ({self.serving_size})"
