"""tests config module."""

import pytest
import requests_mock as requests_mock_lib
from pytest_factoryboy import register

from .exercises.factories import DayStepsFactory, ExerciseFactory
from .foods.factories.cupboard import (
    CupboardItemConsumptionFactory,
    CupboardItemFactory,
)
from .foods.factories.food import FoodFactory
from .foods.factories.product import FoodProductFactory
from .foods.factories.recipe import RecipeFactory, RecipeIngredientFactory
from .foods.factories.serving import ServingFactory
from .goals.factories import FatPercGoalFactory
from .measurements.factories import MeasurementFactory
from .plans.factories.day import DayFactory
from .plans.factories.intake import IntakeFactory
from .plans.factories.week import WeekPlanFactory
from .users.factories import UserFactory

register(CupboardItemFactory)
register(CupboardItemConsumptionFactory)
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


@pytest.fixture(autouse=True)
def fallback_requests_mock():
    """Mock for requests library.

    This mock will make sure that no test creates a real request that can alter
    production systems. Any kind of request should mocked per test.

    Yields:
        Mock: requests mocked
    """
    with requests_mock_lib.Mocker() as mock:
        mock.register_uri(
            requests_mock_lib.ANY,
            requests_mock_lib.ANY,
            json={
                "mocked request": "This request has been mocked to "
                "prevent tests from contacting the internet. Please, write "
                "an specific mock for your use case."
            },
        )
        yield mock
