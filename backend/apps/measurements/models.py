"""measurements app module module."""

from decimal import Decimal
from typing import Any

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

    body_fat_calculation_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        blank=True,
        null=True,
        editable=False,
        verbose_name="Body fat used for calculations (%)",
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Persist a stable body-fat snapshot for weight-only entries.

        Args:
            *args (Any): positional arguments passed to Django's save method.
            **kwargs (Any): keyword arguments passed to Django's save method.
        """
        calculation_changed = False
        if (
            self.body_fat_perc is None
            and self.body_fat_calculation_perc is None
        ):
            previous_body_fat = Measurement.objects.filter(
                user_id=self.user_id,
                body_fat_perc__isnull=False,
            )
            if self.pk:
                previous_body_fat = previous_body_fat.exclude(pk=self.pk)
            self.body_fat_calculation_perc = (
                previous_body_fat.order_by("-created_at", "-id")
                .values_list("body_fat_perc", flat=True)
                .first()
            )
            calculation_changed = self.body_fat_calculation_perc is not None
        elif (
            self.body_fat_perc is not None
            and self.body_fat_calculation_perc is not None
        ):
            self.body_fat_calculation_perc = None
            calculation_changed = True

        update_fields = kwargs.get("update_fields")
        if calculation_changed and update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {
                "body_fat_calculation_perc"
            }
        super().save(*args, **kwargs)

    @property
    def calculation_body_fat_perc(self) -> Decimal | None:
        """Return the stable body-fat value used for derived values.

        A weight-only entry snapshots the user's most recently entered
        body-fat percentage without claiming that it was measured again.

        Returns:
            Decimal | None: recorded or most recent body-fat percentage.
        """
        if self.body_fat_perc is not None:
            return self.body_fat_perc
        return self.body_fat_calculation_perc

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
