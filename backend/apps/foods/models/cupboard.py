from datetime import datetime
from typing import Any

from django.db import models

from apps.plans.models.intake import Intake

from .food import Food
from .serving import Serving
from ..managers import CupboardItemServingManager


class CupboardItem(models.Model):
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

    def __getattribute__(self, __name: str) -> Any:
        return super().__getattribute__(__name)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.started = self.consumed_perc > 0
        self.finished = self.consumed_perc == 100
        super().save(*args, **kwargs)


class CupboardItemServing(Serving):
    """

    Note: A `CupboardItemServing` will be added to the DB when it's
    planned, not before like `Servings`.
    """

    objects = CupboardItemServingManager()

    item = models.ForeignKey(
        "foods.CupboardItem",
        on_delete=models.CASCADE,
        related_name="servings",
    )
