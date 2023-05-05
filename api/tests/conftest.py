"""tests config module."""


import pytest
from pytest_factoryboy import register

from .foods.factories import (
    FoodFactory,
    RecipeFactory,
    RecipeIngredientFactory,
)
from .goals.factories import FatPercGoalFactory
from .measurements.factories import MeasurementFactory
from .plans.factories import (
    DayFoodFactory,
    DayTrackingFactory,
    WeekPlanFactory,
)
from .users.factories import UserFactory

register(DayFoodFactory)
register(DayTrackingFactory)
register(FatPercGoalFactory)
register(FoodFactory)
register(MeasurementFactory)
register(RecipeFactory)
register(RecipeIngredientFactory)
register(UserFactory)
register(WeekPlanFactory)

register(
    UserFactory,
    "admin_user",
    is_staff=True,
    is_superuser=True,
)


@pytest.fixture
def logged_in_admin_client(db, client, admin_user):
    """Client with an admin user logged in."""
    client.force_login(admin_user)
    return client
