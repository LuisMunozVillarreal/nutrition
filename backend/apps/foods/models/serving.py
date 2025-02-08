"""Serving model module."""

from decimal import Decimal
from typing import Any

from django.core.validators import MinValueValidator
from django.db import models

from apps.libs.utils import round_no_trailing_zeros

from .food import Food
from .nutrients import NUTRIENT_LIST, Nutrients
from .product import FoodProduct
from .units import UNIT_CHOICES, UNIT_CONTAINER, UNIT_GRAM, UNIT_SERVING, UREG


class Serving(Nutrients):
    """Serving model class."""

    food = models.ForeignKey(
        "foods.Food",
        on_delete=models.CASCADE,
        related_name="servings",
    )

    serving_size = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        validators=[MinValueValidator(Decimal("0"))],
        default=100,
        help_text=(
            "Size is the amount of units in the serving. For example, if the "
            "unit is grams and the size is 100, it means 100g. When the "
            "serving unit and the food size unit is the same, then the "
            "size of the serving is the same as the size of the food. "
            "However, when the unit of the serving is 'container' or "
            "'serving', then the size will most certainly differ from the "
            "size, e.g.: size 1 unit container sizes 320g."
        ),
    )

    serving_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default=UNIT_GRAM,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        res = f"{self.food} - {self.serving_size}"
        if self.serving_unit in (UNIT_CONTAINER, UNIT_SERVING):
            res += " "
        res += self.serving_unit

        if self.serving_unit in (UNIT_CONTAINER, UNIT_SERVING):
            res += (
                f" ({round_no_trailing_zeros(self.serving_size)}"
                f"{self.size_unit})"
            )

        return res

    @property
    def size(self) -> Decimal:
        """Get the size of the serving.

        Returns:
            Decimal: the size of the serving.
        """
        if self.serving_unit == UNIT_CONTAINER:
            return Decimal(self.food.size)

        if self.serving_unit == UNIT_SERVING:
            return Decimal(self.food.size) / self.food.num_servings

        # pylint: disable=fixme
        # TODO: if self.unit != self.food.size_unit, the self.size of
        # self.unit needs to be converted to self.food.size_unit first
        # - This might be related to why the `get_portion_for` function is
        #   so convoluted.
        # pylint: enable=fixme
        return Decimal(self.serving_size)

    @property
    def size_unit(self) -> str:
        """Get the size unit of the serving.

        Returns:
            str: the size unit of the serving.
        """
        return self.food.size_unit

    def get_portion_for(self, food: Food, nutrient: str) -> Decimal:
        """Get portion of nutrient for the given food.

        Args:
            food (Food): food to get the nutrient from.
            nutrient (str): nutrient name.

        Returns:
            Decimal: proportion.
        """
        # pylint: disable=fixme
        # TODO: Refactor this unintelligible function
        # pylint: enable=fixme
        value = getattr(food, nutrient) or 0

        unit = self.serving_unit
        size = Decimal(food.nutritional_info_size)
        self_size: int | Decimal = self.serving_size
        if self.serving_unit == UNIT_CONTAINER:
            unit = self.food.size_unit
            size = Decimal(self.food.nutritional_info_size)
            self_size = self.food.size
        elif self.serving_unit == UNIT_SERVING:
            unit = self.food.size_unit
            if FoodProduct.objects.filter(pk=food.pk).exists():
                size = Decimal(self.food.nutritional_info_size)
                self_size = Decimal(self.food.size) / Decimal(
                    self.food.num_servings
                )
            else:
                size = Decimal(self.food.num_servings)

        if unit != food.nutritional_info_unit:
            new_size = UREG.Quantity(
                Decimal(str(food.nutritional_info_size))
            ) * UREG(food.nutritional_info_unit)
            new_size = new_size.to(unit).m
            size = Decimal(new_size)

        return value * self_size / size

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        for nutrient in NUTRIENT_LIST:
            value = getattr(self.food, nutrient)
            if value:
                value = self.get_portion_for(self.food, nutrient)
                setattr(self, nutrient, value)

        super().save(*args, **kwargs)
