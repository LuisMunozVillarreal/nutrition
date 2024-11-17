"""plans.week factories module."""

import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.plans.models import WeekPlan
from tests.measurements.factories import MeasurementFactory
from tests.users.factories import UserFactory


class WeekPlanFactory(DjangoModelFactory):
    """WeekPlanFactory class."""

    class Meta:
        model = WeekPlan

    user = SubFactory(UserFactory)
    measurement = SubFactory(MeasurementFactory)
    start_date = datetime.date(2023, 1, 9)
    protein_g_kg = Decimal("2.5")
    fat_perc = 25
    deficit = Decimal("200")
