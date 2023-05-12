"""plans app factories module."""


import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.plans.models import Day, Intake, WeekPlan

from ..foods.factories import FoodProductFactory
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
    deficit = 100


class DayFactory(DjangoModelFactory):
    """DayFactory class."""

    class Meta:
        model = Day

    plan = SubFactory(WeekPlanFactory)
    day = datetime.date(2023, 1, 9)


class IntakeFactory(DjangoModelFactory):
    """IntakeFactory class."""

    class Meta:
        model = Intake

    day = SubFactory(DayFactory)
    food = SubFactory(FoodProductFactory)
    planned_time = datetime.time(12, 0)
    meal = Intake.MEAL_BREAKFAST
    meal_order = 0
    serving_size = 100
    serving_unit = "g"
