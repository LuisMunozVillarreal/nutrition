"""week plan tests module."""


import datetime
from decimal import Decimal

import pytest


@pytest.fixture
def yesterday(mocker):
    """Date in the past mock."""
    mock = mocker.patch(
        "apps.plans.models.week.datetime",
        wraps=datetime,
    )
    mock.date.today.return_value = datetime.date(2022, 3, 9)
    return mock


def test_calorie_intake(db, day_food, yesterday):
    """Calculate calorie intake correctly."""
    assert day_food.day.plan.calorie_intake == 0


def test_calorie_expenditure(db, day_food):
    """Calculate calorie expenditure correctly."""
    assert day_food.day.plan.calorie_expenditure == Decimal(
        "1979.135200000000057367799400"
    )


def test_calorie_expenditure_yesterday(db, day_food, yesterday):
    """Calculate calorie expenditure yesterday correctly."""
    assert day_food.day.plan.calorie_expenditure == 0


def test_protein_intake_g(db, day_food):
    """Calculate protein intake in grams correctly."""
    assert day_food.day.plan.protein_intake_g == 25


def test_remaining_protein_intake_g_day(db, day_food, yesterday):
    """Calculate remaining protein intake in grams correctly."""
    assert day_food.day.plan.remaining_protein_g_day == Decimal(
        "235.7499999999999928945726424"
    )


@pytest.fixture
def today(mocker):
    """Date in the past mock."""
    mock = mocker.patch(
        "apps.plans.models.week.datetime",
        wraps=datetime,
    )
    mock.date.today.return_value = datetime.date(2024, 3, 15)
    return mock


def test_calorie_intake_after_today(db, day_food, today):
    """Calculate calorie intake after today correctly."""
    assert day_food.day.plan.calorie_intake == 106
