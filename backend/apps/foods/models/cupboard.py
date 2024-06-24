"""CupboardItem model module."""

from typing import Any

from django.db import models

from ..managers import CupboardItemServingManager
from .serving import Serving


class CupboardItem(models.Model):
    """CupboardItem model class."""

    food = models.ForeignKey(
        "foods.Food",
        on_delete=models.CASCADE,
        related_name="cupboard_items",
    )

    started = models.BooleanField(
        default=False,
    )

    finished = models.BooleanField(
        default=False,
    )

    purchased_at = models.DateTimeField()

    consumed_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        self.started = self.consumed_perc > 0
        self.finished = self.consumed_perc == 100
        super().save(*args, **kwargs)


class CupboardItemServing(Serving):
    """CupboardItemServing model class.

    Note: A `CupboardItemServing` will be added to the DB when it's
    planned, not before like `Servings`.
    """

    objects = CupboardItemServingManager()  # type: ignore

    item = models.ForeignKey(
        "foods.CupboardItem",
        on_delete=models.CASCADE,
        related_name="servings",
    )
