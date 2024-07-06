"""tests config module."""

import pytest
from pytest_factoryboy import register

from .exercises.factories import DayStepsFactory, ExerciseFactory
from .foods.factories import (
    FoodFactory,
    FoodProductFactory,
    RecipeFactory,
    RecipeIngredientFactory,
    ServingFactory,
)
from .goals.factories import FatPercGoalFactory
from .measurements.factories import MeasurementFactory
from .plans.factories import DayFactory, IntakeFactory, WeekPlanFactory
from .users.factories import UserFactory

register(DayFactory)
register(DayStepsFactory)
register(ExerciseFactory)
register(FatPercGoalFactory)
register(FoodFactory)
register(FoodProductFactory)
register(IntakeFactory)
register(MeasurementFactory)
register(RecipeFactory)
register(RecipeIngredientFactory)
register(ServingFactory)
register(UserFactory)
register(WeekPlanFactory)

register(
    UserFactory,
    "admin_user",
    is_staff=True,
    is_superuser=True,
)

register(
    DayFactory,
    "tracked_day",
    tracked=True,
)


@pytest.fixture
def logged_in_admin_client(db, client, admin_user):
    """Client with an admin user logged in."""
    client.force_login(admin_user)
    return client


@pytest.fixture(autouse=True)
def reset_sequence(django_db_reset_sequences):
    """Reset sequences by default."""
