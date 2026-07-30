"""CupboardItem model module."""

from decimal import Decimal
from typing import Any

from django.db import models, router, transaction

from .product import FoodProduct
from .recipe import Recipe
from .units import UNIT_CHOICES, UNIT_CONTAINER, UNIT_SERVING


class CupboardItem(models.Model):
    """CupboardItem model class."""

    owner = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="cupboard_items",
        null=True,
        blank=True,
    )

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

    manual_consumed_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=(
            "Consumption entered manually, before linked recipe and intake "
            "consumptions are added."
        ),
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

    @property
    def consumed_servings(self) -> Decimal:
        """Get consumed servings.

        Returns:
            Decimal: consumed servings.
        """
        return self.food.num_servings * self.consumed_perc / 100

    @property
    def remaining_servings(self) -> Decimal:
        """Get remaining servings.

        Returns:
            Decimal: remaining servings.
        """
        return self.food.num_servings - self.consumed_servings

    @property
    def energy_kcal_per_serving(self) -> Decimal:
        """Get energy in kcal per serving.

        Returns:
            Decimal: energy in kcal per serving.
        """
        return self.food.energy_kcal / self.food.num_servings

    @property
    def fat_g_per_serving(self) -> Decimal:
        """Get fat in grams per serving.

        Returns:
            Decimal: fat in grams per serving.
        """
        return self.food.fat_g / self.food.num_servings

    @property
    def carbs_g_per_serving(self) -> Decimal:
        """Get carbs in grams per serving.

        Returns:
            Decimal: carbs in grams per serving.
        """
        return self.food.carbs_g / self.food.num_servings

    @property
    def protein_g_per_serving(self) -> Decimal:
        """Get protein in grams per serving.

        Returns:
            Decimal: protein in grams per serving.
        """
        return self.food.protein_g / self.food.num_servings

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.

        Raises:
            ValueError: if the requested total is below linked consumption.
        """
        if self._state.adding:
            if not self.manual_consumed_perc and self.consumed_perc:
                self.manual_consumed_perc = self.consumed_perc
        else:
            previous = (
                type(self)
                .objects.only("consumed_perc", "manual_consumed_perc")
                .get(pk=self.pk)
            )
            if (
                self.consumed_perc != previous.consumed_perc
                and self.manual_consumed_perc == previous.manual_consumed_perc
            ):
                linked_consumed_perc = (
                    previous.consumed_perc - previous.manual_consumed_perc
                )
                if self.consumed_perc < linked_consumed_perc:
                    raise ValueError(
                        "consumed_perc cannot be less than linked consumption"
                    )
                self.manual_consumed_perc = (
                    self.consumed_perc - linked_consumed_perc
                )
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                        "manual_consumed_perc"
                    }

        self.started = self.consumed_perc > 0
        self.finished = self.consumed_perc == 100
        super().save(*args, **kwargs)


class CupboardItemConsumption(models.Model):
    """CupboardItemConsumption model class.

    A `CupboardItemConsumption` will be added to the DB when it's
    planned, not before like, `Servings`.

    The reason why is because it's unknown what servings will be used to
    consume a product.
    """

    item = models.ForeignKey(
        "foods.CupboardItem",
        on_delete=models.CASCADE,
        related_name="consumptions",
    )

    serving = models.ForeignKey(
        "foods.Serving",
        on_delete=models.CASCADE,
        related_name="cupboard_items",
    )

    num_servings = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=1,
        help_text="Serving quantity captured when this consumption was linked.",
    )

    consumed_amount = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        default=0,
        editable=False,
    )

    consumed_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default="",
        editable=False,
    )

    intake = models.OneToOneField(
        "plans.Intake",
        on_delete=models.CASCADE,
        related_name="cupboard_item_consumption",
        null=True,
    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Atomically capture and apply a linked cupboard consumption.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        with transaction.atomic(using=using):
            unit = self.serving.serving_unit
            if unit in (UNIT_CONTAINER, UNIT_SERVING):
                unit = self.serving.size_unit
            self.consumed_amount = self.serving.size * self.num_servings
            self.consumed_unit = unit
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "consumed_amount",
                    "consumed_unit",
                }
            super().save(*args, **kwargs)
