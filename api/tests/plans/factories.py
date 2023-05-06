"""plans app factories module."""


import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.plans.models import DayFood, DayTracking, WeekPlan

from ..foods.factories import FoodFactory
from ..measurements.factories import MeasurementFactory
from ..users.factories import UserFactory


class WeekPlanFactory(DjangoModelFactory):
    """WeekPlanFactory class."""

    class Meta:
        model = WeekPlan

    user = SubFactory(UserFactory)
    measurement = SubFactory(MeasurementFactory)
    start_date = datetime.date(2023, 1, 9)
    protein_kg = Decimal("2.5")
    fat_perc = 25


class DayTrackingFactory(DjangoModelFactory):
    """DayTrackingFactory class."""

    class Meta:
        model = DayTracking

    plan = SubFactory(WeekPlanFactory)
    day = datetime.date(2023, 1, 9)


class DayFoodFactory(DjangoModelFactory):
    """DayFoodFactory class."""

    class Meta:
        model = DayFood

    day = SubFactory(DayTrackingFactory)
    food = SubFactory(FoodFactory)
    time = datetime.time(12, 0)
    meal = DayFood.MEAL_BREAKFAST
    meal_order = 0
    serving_size = 100
    serving_unit = "g"
