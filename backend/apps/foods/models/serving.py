"""Serving model module."""

from decimal import Decimal
from typing import Any

from django.db import models
from pint import UnitRegistry

from .food import Food
from .nutrients import NUTRIENT_LIST, Nutrients
from .product import FoodProduct
from .units import UNIT_CHOICES, UNIT_CONTAINER, UNIT_GRAM, UNIT_SERVING


class Serving(Nutrients):
    """Serving model class."""

    UREG = UnitRegistry()

    food = models.ForeignKey(
        "foods.Food",
        on_delete=models.CASCADE,
        related_name="servings",
    )

    size = models.PositiveIntegerField(
        default=100,
        help_text=(
            "Size is the amount of units in the serving. For example, if the "
            "unit is grams and the size is 100, it means 100g. When the "
            "serving unit and the food weight unit is the same, then the "
            "weight of the serving is the same as the weight of the serving. "
            "However, when the unit of the serving is 'container' or "
            "'serving', then the weight will most certainly differ from the "
            "size, e.g.: size 1 unit container weights 320g."
        ),
    )

    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default=UNIT_GRAM,
    )

    def __str__(self):
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        res = f"{self.food} - {self.size}"
        if self.unit in (UNIT_CONTAINER, UNIT_SERVING):
            res += " "
        res += self.unit

        if self.unit in (UNIT_CONTAINER, UNIT_SERVING):
            res += f" ({self.weight}{self.weight_unit})"

        return res

    @property
    def weight(self) -> int:
        """Get the weight of the serving.

        Returns:
            int: the weight of the serving.
        """
        if self.unit == UNIT_CONTAINER:
            return self.food.weight

        if self.unit == UNIT_SERVING:
            return int(self.food.weight // self.food.num_servings)

        return self.size

    @property
    def weight_unit(self) -> str:
        """Get the weight unit of the serving.

        Returns:
            str: the weight unit of the serving.
        """
        return self.food.weight_unit

    def get_portion_for(self, food: Food, nutrient: str) -> Decimal:
        """Get portion of nutrient for the given food.

        Args:
            food (Food): food to get the nutrient from.
            nutrient (str): nutrient name.

        Returns:
            Decimal: proportion.
        """
        value = getattr(food, nutrient) or 0

        unit = self.unit
        size = Decimal(food.nutritional_info_size)
        self_size: int | Decimal = self.size
        if self.unit == UNIT_CONTAINER:
            unit = self.food.weight_unit
            size = Decimal(self.food.nutritional_info_size)
            self_size = self.food.weight
        elif self.unit == UNIT_SERVING:
            unit = self.food.weight_unit
            if FoodProduct.objects.filter(pk=food.pk).exists():
                size = Decimal(self.food.nutritional_info_size)
                self_size = Decimal(self.food.weight) / Decimal(
                    self.food.num_servings
                )
            else:
                size = Decimal(self.food.num_servings)

        if unit != food.nutritional_info_unit:
            new_size = self.UREG.Quantity(
                Decimal(str(food.nutritional_info_size))
            ) * self.UREG(food.nutritional_info_unit)
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
