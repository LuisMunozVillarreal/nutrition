"""CupboardItem model module."""

from typing import Any

from django.db import models

from ..managers import CupboardItemServingManager
from .product import FoodProduct
from .recipe import Recipe
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

    def __str__(self) -> str:
        """Get string representation of the object.

        Return:
            str: string representation of the object.
        """
        qs1 = FoodProduct.objects.filter(pk=self.food.pk)
        if qs1.exists():
            return str(qs1.first())

        qs2 = Recipe.objects.filter(pk=self.food.pk)
        if qs2.exists():
            return str(qs2.first())

        return str(self.food)

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
    The reason why is because it's unknown what servings will be used to
    consume a product
    """

    objects = CupboardItemServingManager()  # type: ignore

    item = models.ForeignKey(
        "foods.CupboardItem",
        on_delete=models.CASCADE,
        related_name="servings",
    )
