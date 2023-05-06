"""plans week model tests module."""


import datetime
from decimal import Decimal

import pytest


def test_tdee_target(db, week_plan):
    """Calculate TDEE target correctly."""
    assert week_plan.tdee_target == Decimal("2721.3109")


def test_twee_target(db, week_plan):
    """Calculate TWEE target correctly."""
    assert week_plan.twee_target == Decimal("19049.1763")


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
    assert result == week_plan.twee_target
    assert before_start.datetime.now.called


def test_before_start_with_one_day(db, day_tracking, before_start):
    """Day before the plan start doesn't take into account the day."""
    # Given
    plan = day_tracking.plan

    # When
    result = plan.remaining_kcals()

    # Then
    assert result == plan.twee_target
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
    db, day_food, after_start, exercise, day_steps
):
    """Past deficit day doesn't count for the total."""
    # Given
    plan = day_food.day.plan

    # When
    result = plan.remaining_kcals()

    # Then
    assert result == plan.twee_target - 3 * plan.tdee_target
    assert after_start.datetime.now.called


def test_after_start_with_one_past_excess_day(db, day_food, after_start):
    """Past excess day is taken into account for the total."""
    # Given
    day_food.serving_size = 10000
    day_food.save()
    plan = day_food.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    expected = (
        plan.twee_target - 3 * plan.tdee_target - day_food.day.calorie_surplus
    )
    assert result == expected
    assert after_start.datetime.now.called


def test_after_start_with_one_future_day(db, day_food, after_start):
    """Future day doesn't count for the total."""
    # Given
    day_food.day.day = datetime.date(2023, 1, 13)
    day_food.day.save()
    plan = day_food.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    assert result == plan.twee_target - 3 * plan.tdee_target
    assert after_start.datetime.now.called


def test_after_start_with_non_finished_day(db, day_food, after_start):
    """Non finished day is taken into account for the total."""
    # Given
    day_food.day.day = datetime.date(2023, 1, 12)
    day_food.day.save()
    plan = day_food.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    assert (
        result == plan.twee_target - 3 * plan.tdee_target - day_food.calories
    )
    assert after_start.datetime.now.called


def test_future_food_same_day(db, day_food, after_start):
    """Food in the future on the same day isn't taken into account."""
    # Given
    day_food.day.day = datetime.date(2023, 1, 12)
    day_food.day.save()
    day_food.time = datetime.time(20, 0)
    day_food.save()
    plan = day_food.day.plan

    # When
    result = plan.remaining_kcals()

    #  Then
    expected = plan.twee_target - 3 * plan.tdee_target
    assert result == expected
    assert after_start.datetime.now.called


@pytest.fixture
def plan_two_days(db, day_tracking, day_tracking_factory, day_food_factory):
    """Plan with two days added."""
    second_day_tracking = day_tracking_factory(
        plan=day_tracking.plan, day=datetime.date(2023, 1, 10)
    )
    day_food_factory(day=second_day_tracking, serving_size=1000)
    return day_tracking.plan


def test_after_start_with_two_days_after_today_three(
    plan_two_days, after_start
):
    """Missing days are made up with tdee instead."""
    # Given
    plan = plan_two_days

    # When
    result = plan.remaining_kcals()

    # Then
    assert result <= plan.twee_target
    assert result == plan.twee_target - 3 * plan.tdee_target
    assert after_start.datetime.now.called


@pytest.fixture
def plan_three_days(plan_two_days, day_tracking_factory, day_food_factory):
    """Plan with two days added."""
    day_tracking_factory(plan=plan_two_days, day=datetime.date(2023, 1, 15))
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
    assert result <= plan.twee_target
    assert result == plan.twee_target - 3 * plan.tdee_target
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


def test_protein_no_remaining_days(db, day_food):
    """No protein remaining when there is no remaining days."""
    assert day_food.day.plan.remaining_protein_g_day == 0


#
# calorie_goal tests
#


def test_future_day(plan_three_days, after_start):
    """Future day's calorie goal is only about the remaining kcals."""
    # Given
    plan = plan_three_days
    day = plan_three_days.days.first()
    assert day.day == datetime.date(2023, 1, 15)

    # When
    result = day.calorie_goal

    # Then
    assert result == plan.tdee_target


def test_past_day(plan_three_days, after_start):
    """Past day's calorie goal checks the previous days."""
    # Given
    plan = plan_three_days
    day = plan_three_days.days.last()
    assert day.day == datetime.date(2023, 1, 9)

    # When
    result = day.calorie_goal

    # Then
    assert result == plan.tdee_target
    assert not after_start.datetime.now.called
