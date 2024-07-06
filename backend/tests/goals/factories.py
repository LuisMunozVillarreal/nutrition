"""goals app factories module."""

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.goals.models import FatPercGoal

from ..users.factories import UserFactory


class FatPercGoalFactory(DjangoModelFactory):
    """FatPercGoalFactory class."""

    class Meta:
        model = FatPercGoal

    user = SubFactory(UserFactory)
    body_fat_perc = 14
