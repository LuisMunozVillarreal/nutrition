"""apps.exercises factories."""

import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.exercises.models import DaySteps, Exercise

from ..plans.factories import DayFactory


class ExerciseFactory(DjangoModelFactory):
    """Exercise factory class."""

    class Meta:
        model = Exercise

    day = SubFactory(DayFactory)
    time = datetime.time(20, 26)
    type = "walk"
    kcals = 100
    duration = datetime.timedelta(minutes=30)
    distance = Decimal("1.01")


class DayStepsFactory(DjangoModelFactory):
    """DaySteps factory class."""

    class Meta:
        model = DaySteps

    day = SubFactory(DayFactory)
    steps = 1000
