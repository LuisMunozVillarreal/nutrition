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


def test_calorie_intake(db, intake, yesterday):
    """Calculate calorie intake correctly."""
    assert intake.day.plan.calorie_intake == 0


def test_calorie_expenditure(db, intake):
    """Calculate calorie expenditure correctly."""
    assert intake.day.plan.calorie_expenditure == Decimal("2077.04872")


def test_calorie_expenditure_yesterday(db, intake, yesterday):
    """Calculate calorie expenditure yesterday correctly."""
    assert intake.day.plan.calorie_expenditure == 0


def test_protein_intake_g(db, intake):
    """Calculate protein intake in grams correctly."""
    assert intake.day.plan.protein_intake_g == 25


def test_remaining_protein_intake_g_day(db, intake, yesterday):
    """Calculate remaining protein intake in grams correctly."""
    assert intake.day.plan.remaining_protein_g_day == Decimal("235.75")


@pytest.fixture
def today(mocker):
    """Date in the past mock."""
    mock = mocker.patch(
        "apps.plans.models.week.datetime",
        wraps=datetime,
    )
    mock.date.today.return_value = datetime.date(2024, 3, 15)
    return mock


def test_calorie_intake_after_today(db, intake, today):
    """Calculate calorie intake after today correctly."""
    assert intake.day.plan.calorie_intake == 106
