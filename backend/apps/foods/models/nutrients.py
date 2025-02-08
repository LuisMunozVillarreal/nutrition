"""Nutriens model module."""

from decimal import Decimal
from typing import Any

from django.db import models

from apps.libs.basemodel import BaseModel


class Nutrients(BaseModel):
    """Nutriens model class."""

    class Meta:
        abstract = True

    energy_kcal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Energy (kcal)",
    )

    protein_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Protein (g)",
    )

    fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Total Fat (g)",
    )

    saturated_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    polyunsaturated_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    monosaturated_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    trans_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Total Carbs (g)",
        default=0,
    )

    fibre_carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    salt_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    sugar_carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    sodium_mg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    potassium_mg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    vitamin_a_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    vitamin_c_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    calcium_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    iron_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    abv_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Alcohol by volume (%)",
    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        if self.salt_g:
            self.sodium_mg = self.salt_g / Decimal("2.5") * 1000
        elif self.sodium_mg:
            self.salt_g = self.sodium_mg * Decimal("2.5") / 1000

        super().save(*args, **kwargs)


NUTRIENT_LIST = [
    i
    for i in Nutrients.__dict__
    if i[:1] not in ["_", "M"] and i not in BaseModel.__dict__ and i != "save"
]
