"""measurements app module module."""


from decimal import Decimal

from django.db import models

from apps.libs.basemodel import BaseModel


class Measurement(BaseModel):
    """Measuremnt class."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="measurements",
    )

    fat_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
    )

    weight = models.DecimalField(
        max_digits=10,
        decimal_places=1,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return f"Measurement - {self.created_at.strftime('%a %d %h %y')}"

    @property
    def fat_kg(self) -> Decimal:
        """Get fat in kgs.

        Returns:
            Decimal: fat in kgs.
        """
        return self.weight * self.fat_perc / 100

    @property
    def bmr_kma(self) -> Decimal:
        """Get base metabolic rate using KMA formula.

        Returns:
            Decimal: base metabolic rate using KMA formula.
        """
        if not self.weight:
            return Decimal("0")

        return 370 + (
            Decimal("21.6") * ((self.weight * (100 - self.fat_perc) / 100))
        )

    @property
    def bmr(self) -> Decimal:
        """Get base metabolic rate.

        Returns:
            Decimal: base metabolic rate.
        """
        return self.bmr_kma
