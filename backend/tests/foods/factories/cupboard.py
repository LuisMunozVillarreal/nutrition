"""foods.cupboard factories module."""

from datetime import datetime, timezone

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.foods.models import CupboardItem, CupboardItemConsumption
from tests.plans.factories.intake import IntakeFactory

from .food import FoodFactory
from .serving import ServingFactory


class CupboardItemFactory(DjangoModelFactory):
    """CupboardItemFactory class."""

    class Meta:
        model = CupboardItem

    food = SubFactory(FoodFactory)
    purchased_at = datetime(2020, 12, 21, 0, 0, 0, tzinfo=timezone.utc)


class CupboardItemConsumptionFactory(DjangoModelFactory):
    """CupboardItemConsumptionFactory class."""

    class Meta:
        model = CupboardItemConsumption

    item = SubFactory(CupboardItemFactory)
    serving = SubFactory(ServingFactory)
    intake = SubFactory(IntakeFactory)
