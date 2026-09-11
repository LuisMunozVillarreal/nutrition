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

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Customize the generated day instead of inserting a duplicate."""
        plan = kwargs.pop("plan")
        day_num = kwargs.pop("day_num")
        return model_class.objects.update_or_create(
            plan=plan, day_num=day_num, defaults=kwargs
        )[0]

    plan = SubFactory(WeekPlanFactory)
    day = datetime.date(2023, 1, 9)
    day_num = 1
    deficit = Decimal("220")
    tracked = True
    protein_g_goal = Decimal("235.8")
