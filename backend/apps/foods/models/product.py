"""FoodProduct model module."""

from django.db import models

from apps.libs.utils import round_no_trailing_zeros
from config.settings import CARB_KCAL_GRAM, FAT_KCAL_GRAM, PROTEIN_KCAL_GRAM

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

    @property
    def energy_meets_macros(self) -> bool:
        """Check if energy meets macros.

        Returns:
            bool: True if energy meets macros, False otherwise.
        """
        return (
            self.energy_kcal
            == self.protein_g * PROTEIN_KCAL_GRAM
            + self.fat_g * FAT_KCAL_GRAM
            + self.carbs_g * CARB_KCAL_GRAM
        )

    def check_products(self):
        if self.energy_meets_macros:
            print(f">>>> {self}")
        else:
            macros_energy = (
                self.protein_g * PROTEIN_KCAL_GRAM
                + self.fat_g * FAT_KCAL_GRAM
                + self.carbs_g * CARB_KCAL_GRAM
            )
            perc = "---"
            if macros_energy > 0:
                perc = round(self.energy_kcal / macros_energy * 100, 1)
            print(
                f"**** {self.energy_kcal - macros_energy}\t{perc} {self} - "
                f"{self.energy_kcal} - {macros_energy}"
            )
