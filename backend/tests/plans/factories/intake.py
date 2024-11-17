"""plans.intake factories module."""

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.plans.models import Intake
from tests.foods.factories.serving import ServingFactory

from .day import DayFactory


class IntakeFactory(DjangoModelFactory):
    """IntakeFactory class."""

    class Meta:
        model = Intake

    day = SubFactory(DayFactory)
    food = SubFactory(ServingFactory)
    meal = Intake.MEAL_BREAKFAST
    meal_order = 0
