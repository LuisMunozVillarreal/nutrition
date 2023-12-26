"""Food model module."""


from django.db import models

from .nutrients import Nutrients
from .units import UNIT_CHOICES, UNIT_GRAM


class Food(Nutrients):
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

    nutritional_info_size = models.PositiveIntegerField(
        default=100,
    )

    nutritional_info_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default=UNIT_GRAM,
    )

    weight = models.PositiveIntegerField(
        default=100,
    )

    weight_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default=UNIT_GRAM,
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
        if self.brand:
            return f"{self.brand} {self.name}"

        return self.name
