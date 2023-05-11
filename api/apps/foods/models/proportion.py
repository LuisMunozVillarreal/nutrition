"""FoodProportion model module."""


from abc import abstractmethod
from decimal import Decimal
from typing import Any

from pint import UnitRegistry

from .food import Food
from .nutrients import NUTRIENT_LIST
from .quantity import FoodQuantity


class FoodProportion(FoodQuantity):
    """FoodProportion model class."""

    class Meta:
        abstract = True

    UREG = UnitRegistry()

    @property
    @abstractmethod
    def food(self) -> Food:
        """Get food abstract method."""

    def get_portion_for(self, food: Food, nutrient: str) -> Decimal:
        """Get portion of nutrient for the given food.

        Args:
            food (Food): food to get the nutrient from.
            nutrient (str): nutrient name.

        Returns:
            Decimal: proportion.
        """
        size = food.serving_size

        if self.serving_unit != food.serving_unit:
            size = Decimal(food.serving_size) * self.UREG(food.serving_unit)
            size = size.to(self.serving_unit).m

        size = Decimal(size)
        value = getattr(food, nutrient)

        return value * self.serving_size / size

    def save(self, *args: list, **kwargs: dict[Any, Any]) -> None:
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
