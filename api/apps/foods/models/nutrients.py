"""Nutriens model module."""


from django.db import models

from apps.libs.basemodel import BaseModel


class Nutrients(BaseModel):
    """Nutriens model class."""

    class Meta:
        abstract = True

    calories = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    protein_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
    )

    fat_g = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Total Fat (g)",
        blank=True,
        null=True,
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
        blank=True,
        null=True,
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
