"""Nutriens model module."""

from django.db import models

from apps.libs.basemodel import BaseModel


class Nutrients(BaseModel):
    """Nutriens model class."""

    class Meta:
        abstract = True

    energy = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name="Energy (kcal)",
    )

    protein_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name="Protein (g)",
    )

    fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        verbose_name="Total Fat (g)",
    )

    saturated_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    polyunsaturated_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    monosaturated_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    trans_fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Total Carbs (g)",
        default=0,
    )

    fiber_carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    sugar_carbs_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    sodium_mg = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    potassium_mg = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    vitamin_a_perc = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    vitamin_c_perc = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    calcium_perc = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    iron_perc = models.PositiveIntegerField(
        blank=True,
        null=True,
    )


NUTRIENT_LIST = [
    i
    for i in Nutrients.__dict__
    if i[:1] not in ["_", "M"] and i not in BaseModel.__dict__
]
