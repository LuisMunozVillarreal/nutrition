"""plans week model tests module."""


import datetime
from decimal import Decimal

import pytest


def test_estimated_tdee(db, week_plan):
    """Calculate TDEE target correctly."""
    assert week_plan.estimated_tdee == Decimal("2621.3109")


def test_estimated_twee(db, week_plan):
    """Calculate TWEE target correctly."""
    assert week_plan.estimated_twee == Decimal("18349.1763")


#
# remaining_kcals tests
#


@pytest.fixture
def before_start(mocker):
    """Date in the past mock."""
    mock = mocker.patch(
        "apps.plans.models.week.datetime",
        wraps=datetime,
    )
    mock.datetime.now.return_value = datetime.datetime(2019, 3, 8, 12, 0)
    return mock


def test_no_days(db, week_plan, before_start):
    """No days in the plan use twee target."""
    # When
    result = week_plan.remaining_kcals()

    # Then
    assert result == week_plan.estimated_twee
    assert before_start.datetime.now.called


def test_before_start_with_one_day(db, day, before_start):
    """Day before the plan start doesn't take into account the day."""
    # Given
    plan = day.plan

    # When
    result = plan.remaining_kcals()

    # Then
    assert result == plan.estimated_twee
    assert before_start.datetime.now.called


@pytest.fixture
def after_start(mocker):
    """Date in the future mock."""
    mock = mocker.patch(
        "apps.plans.models.week.datetime",
        wraps=datetime,
    )
    mock.datetime.now.return_value = datetime.datetime(2023, 1, 12, 12, 0)
    return mock


def test_after_start_with_one_past_deficit_day(
    db, intake, after_start, exercise, day_steps
):
    """Past deficit day doesn't count for the total."""
    # Given
    plan = intake.day.plan

    # When
    result = plan.remaining_kcals()

    # Then
    assert result == plan.estimated_twee - 3 * plan.estimated_tdee
    assert after_start.datetime.now.called


def test_after_start_with_one_past_excess_day(db, intake, after_start):
    """Past excess day is taken into account for the total."""
    # Given
    intake.serving_size = 10000
    intake.save()
    plan = intake.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    expected = (
        plan.estimated_twee
        - 3 * plan.estimated_tdee
        - intake.day.calorie_surplus
    )
    assert result == expected
    assert after_start.datetime.now.called


def test_after_start_with_one_future_day(db, intake, after_start):
    """Future day doesn't count for the total."""
    # Given
    intake.day.day = datetime.date(2023, 1, 13)
    intake.day.save()
    plan = intake.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    assert result == plan.estimated_twee - 3 * plan.estimated_tdee
    assert after_start.datetime.now.called


def test_after_start_with_non_finished_day(db, intake, after_start):
    """Non finished day is taken into account for the total."""
    # Given
    intake.day.day = datetime.date(2023, 1, 12)
    intake.day.save()
    plan = intake.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    assert (
        result
        == plan.estimated_twee - 3 * plan.estimated_tdee - intake.calories
    )
    assert after_start.datetime.now.called


def test_future_food_same_day(db, intake, after_start):
    """Food in the future on the same day isn't taken into account."""
    # Given
    intake.day.day = datetime.date(2023, 1, 12)
    intake.day.save()
    intake.time = datetime.time(20, 0)
    intake.save()
    plan = intake.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    expected = plan.estimated_twee - 3 * plan.estimated_tdee
    assert result == expected
    assert after_start.datetime.now.called


@pytest.fixture
def plan_two_days(db, day, day_factory, intake_factory):
    """Plan with two days added."""
    second_day = day_factory(plan=day.plan, day=datetime.date(2023, 1, 10))
    intake_factory(day=second_day, serving_size=1000)
    return day.plan


def test_after_start_with_two_days_after_today_three(
    plan_two_days, after_start
):
    """Missing days are made up with tdee instead."""
    # Given
    plan = plan_two_days

    # When
    result = plan.remaining_kcals()

    # Then
    assert result <= plan.estimated_twee
    assert result == plan.estimated_twee - 3 * plan.estimated_tdee
    assert after_start.datetime.now.called


@pytest.fixture
def plan_three_days(plan_two_days, day_factory, intake_factory):
    """Plan with two days added."""
    day_factory(plan=plan_two_days, day=datetime.date(2023, 1, 15))
    return plan_two_days


def test_after_start_with_three_days_after_today_three(
    plan_three_days, after_start
):
    """Past missing days are made up w/ tdee w/o considering future days."""
    # Given
    plan = plan_three_days

    # When
    result = plan.remaining_kcals()

    # Then
    assert result <= plan.estimated_twee
    assert result == plan.estimated_twee - 3 * plan.estimated_tdee
    assert after_start.datetime.now.called


@pytest.fixture
def next_week(mocker):
    """Week in the future mock."""
    mock = mocker.patch(
        "apps.plans.models.week.datetime",
        wraps=datetime,
    )
    mock.datetime.now.return_value = datetime.datetime(2023, 1, 22, 12, 0)
    return mock


def test_protein_no_remaining_days(db, intake):
    """No protein remaining when there is no remaining days."""
    assert intake.day.plan.remaining_protein_g_day == 0


#
# estimated_calorie_goal tests
#


def test_future_day(plan_three_days, after_start):
    """Future day's calorie goal is only about the remaining kcals."""
    # Given
    plan = plan_three_days
    day = plan_three_days.days.first()
    assert day.day == datetime.date(2023, 1, 15)

    # When
    result = day.estimated_calorie_goal

    # Then
    assert result == plan.estimated_tdee


def test_past_day(plan_three_days, after_start):
    """Past day's calorie goal checks the previous days."""
    # Given
    plan = plan_three_days
    day = plan_three_days.days.last()
    assert day.day == datetime.date(2023, 1, 9)

    # When
    result = day.estimated_calorie_goal

    # Then
    assert result == plan.estimated_tdee
    assert not after_start.datetime.now.called
