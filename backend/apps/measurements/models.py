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

    body_fat_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Body fat (%)",
    )

    weight = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Weight (kg)",
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        # For some reason pylint_django it's failing.
        # I believe it's due to protobuf being downgraded due to google-genai
        # pylint: disable=no-member,fixme
        # TODO: Remove this ones protobuf is back to 5.x.x
        return f"Measurement - {self.created_at.strftime('%a %d %h %y')}"

    @property
    def fat_kg(self) -> Decimal:
        """Get fat in kgs.

        Returns:
            Decimal: fat in kgs.
        """
        return self.weight * self.body_fat_perc / 100

    @property
    def bmr_kma(self) -> Decimal:
        """Get base metabolic rate using KMA formula.

        Returns:
            Decimal: base metabolic rate using KMA formula.
        """
        if not self.weight:
            return Decimal("0")

        return 370 + (
            Decimal("21.6")
            * (
                (
                    self.weight
                    * (Decimal("100") - self.body_fat_perc)
                    / Decimal("100")
                )
            )
        )

    @property
    def bmr(self) -> Decimal:
        """Get base metabolic rate.

        Returns:
            Decimal: base metabolic rate.
        """
        return self.bmr_kma
