"""Food model module."""


from django.db import models

from .nutrients import Nutrients
from .quantity import FoodQuantity


class Food(Nutrients, FoodQuantity):
    """Food model class."""

    brand = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    name = models.CharField(
        max_length=255,
    )

    url = models.URLField(
        blank=True,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        if self.brand:
            return f"{self.brand} {self.name}"

        return self.name
