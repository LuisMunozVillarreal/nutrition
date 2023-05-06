"""apps.exercises factories."""


import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.exercises.models import DaySteps, Exercise

from ..users.factories import UserFactory


class ExerciseFactory(DjangoModelFactory):
    """Exercise factory class."""

    class Meta:
        model = Exercise

    user = SubFactory(UserFactory)
    date_time = datetime.datetime(2023, 1, 9, 20, 26).astimezone()
    type = "walk"
    kcals = 100
    duration = datetime.timedelta(minutes=30)
    distance = Decimal("1.01")


class DayStepsFactory(DjangoModelFactory):
    """DaySteps factory class."""

    class Meta:
        model = DaySteps

    user = SubFactory(UserFactory)
    day = datetime.date(2023, 1, 9)
    steps = 1000
