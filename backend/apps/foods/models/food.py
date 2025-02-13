"""Food model module."""

from decimal import Decimal
from typing import Any

from django.core.validators import MinValueValidator
from django.db import models

# TODO: Remove this when the stubs are available - pylint: disable=fixme
from taggit.managers import TaggableManager  # type: ignore[import-untyped]

from .nutrients import Nutrients
from .units import UNIT_CHOICES, UNIT_FLUID_OUNCE, UNIT_GRAM, UREG


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

    tags = TaggableManager(
        blank=True,
    )

    nutritional_info_size = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        validators=[MinValueValidator(Decimal("0"))],
        default=100,
    )

    nutritional_info_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default=UNIT_GRAM,
    )

    size = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        validators=[MinValueValidator(Decimal("0"))],
        default=100,
    )

    size_unit = models.CharField(
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        if self.abv_perc:
            self.energy_kcal = (
                (
                    UREG.Quantity(self.nutritional_info_size)
                    * UREG(self.nutritional_info_unit)
                )
                .to(UNIT_FLUID_OUNCE)
                .m
                * Decimal("2.5")
                * self.abv_perc
            )

        super().save(*args, **kwargs)
