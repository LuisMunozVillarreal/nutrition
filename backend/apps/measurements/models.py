"""measurements app module module."""

from decimal import Decimal
from functools import cached_property

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
        blank=True,
        null=True,
    )

    weight = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Weight (kg)",
    )

    class Meta(BaseModel.Meta):
        """Measurement database metadata."""

        abstract = False
        indexes = [
            models.Index(
                fields=["user", "-created_at", "-id"],
                name="measurement_latest_idx",
            )
        ]

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return f"Measurement - {self.created_at.strftime('%a %d %h %y')}"

    @cached_property
    def calculation_body_fat_perc(self) -> Decimal | None:
        """Return body fat to use for derived values.

        A weight-only entry reuses the user's most recently entered body-fat
        percentage without claiming that it was measured again.

        Returns:
            Decimal | None: recorded or most recent body-fat percentage.
        """
        if self.body_fat_perc is not None:
            return self.body_fat_perc

        if not self.user_id:
            return None

        return (
            type(self)
            .objects.filter(
                user_id=self.user_id,
                body_fat_perc__isnull=False,
            )
            .order_by("-created_at", "-id")
            .values_list("body_fat_perc", flat=True)
            .first()
        )

    @property
    def fat_kg(self) -> Decimal:
        """Get fat in kgs.

        Returns:
            Decimal: fat in kgs, or zero when body fat is unavailable.
        """
        body_fat_perc = self.calculation_body_fat_perc
        if body_fat_perc is None:
            return Decimal("0")
        return self.weight * body_fat_perc / 100

    @property
    def bmr_kma(self) -> Decimal:
        """Get base metabolic rate using KMA formula.

        Returns:
            Decimal: base metabolic rate, or zero when body fat is unavailable.
        """
        if not self.weight:
            return Decimal("0")

        body_fat_perc = self.calculation_body_fat_perc
        if body_fat_perc is None:
            return Decimal("0")

        return 370 + (
            Decimal("21.6")
            * (
                (
                    self.weight
                    * (Decimal("100") - body_fat_perc)
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
