"""foods.serving factories module."""

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.foods.models import Serving

from .food import FoodFactory


class ServingFactory(DjangoModelFactory):
    """ServingFactory class."""

    class Meta:
        model = Serving

    food = SubFactory(FoodFactory)
