"""FoodProportion model module."""


from abc import abstractmethod
from decimal import Decimal
from typing import Any

from pint import UnitRegistry

from .food import Food
from .nutrients import NUTRIENT_LIST, Nutrients
from .quantity import FoodQuantity


class FoodProportion(Nutrients, FoodQuantity):
    """FoodProportion model class."""

    class Meta:
        abstract = True

    UREG = UnitRegistry()

    @property
    @abstractmethod
    def food(self) -> Any:
        """Get food abstract method."""

    def get_portion_for(self, food: Food, nutrient: str) -> Decimal:
        """Get portion of nutrient for the given food.

        Args:
            food (Food): food to get the nutrient from.
            nutrient (str): nutrient name.

        Returns:
            Decimal: proportion.
        """
        size = Decimal(food.serving_size)

        if self.serving_unit != food.serving_unit:
            new_size = self.UREG.Quantity(
                Decimal(str(food.serving_size))
            ) * self.UREG(food.serving_unit)
            new_size = new_size.to(self.serving_unit).m
            size = Decimal(new_size)

        value = getattr(food, nutrient)

        return value * self.serving_size / size

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        for nutrient in NUTRIENT_LIST:
            value = getattr(self.food, nutrient)
            if value:
                food = Food.objects.get(id=self.food.id)
                value = self.get_portion_for(food, nutrient)
                setattr(self, nutrient, value)

        super().save(*args, **kwargs)
