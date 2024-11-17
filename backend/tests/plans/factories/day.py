"""plans.day factories module."""

import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.plans.models import Day

from .week import WeekPlanFactory


class DayFactory(DjangoModelFactory):
    """DayFactory class."""

    class Meta:
        model = Day

    plan = SubFactory(WeekPlanFactory)
    day = datetime.date(2023, 1, 9)
    day_num = 1
    deficit = Decimal("220")
    tracked = True
    protein_g_goal = Decimal("235.8")
