"""plan day tests module."""


from decimal import Decimal

import pytest


def test_protein_g_goal(db, day):
    """Protein goal is correct."""
    assert day.protein_g_goal == Decimal("235.75")


def test_estimated_calorie_goal(db, day):
    """Estimated calorie goal is correct."""
    assert day.calorie_goal == Decimal("2501.3109")


def test_estimated_fat_g_goal(db, day):
    """Estimated fat goal is correct."""
    assert day.fat_g_goal == Decimal("69.48085833333333333333333333")


def test_estimated_carb_g_goal(db, day):
    """Estimated carb goal is correct."""
    assert day.carbs_g_goal == Decimal("468.99579375")


def test_tracked_calorie_goal(db, day_steps, exercise):
    """Tracked calorie goal is correct."""
    # Given
    day_steps.day.tracked = True
    day_steps.day.save()

    # When / Then
    assert day_steps.day.calorie_goal == Decimal("2087.04872")


def test_tracked_calorie_goal_no_steps(db, day, exercise):
    """Tracked calorie goal with no steps is correct."""
    # Given
    day.tracked = True
    day.save()

    # When / Then
    assert day.calorie_goal == Decimal("2057.04872")


def test_increase_day_nutrients(db, intake):
    """Calculate a increase in day nutrients correctly."""
    # When
    intake.serving_size = 200
    intake.save()

    # Then
    assert intake.day.protein_g == 50


def test_decrease_day_nutrients(db, intake):
    """Calculate a decrease in day nutrients correctly."""
    # Given
    day = intake.day
    assert day.protein_g == 25

    # When
    intake.delete()

    # Then
    day.refresh_from_db()
    assert day.protein_g == 0


def test_decrease_day_exercise(db, exercise):
    """Calculate a decrease in day exercise correctly."""
    # Given
    day = exercise.day
    day.tracked = True
    day.save()
    assert day.calorie_goal == Decimal("2057.04872")

    # When
    exercise.delete()

    # Then
    day.refresh_from_db()
    assert day.calorie_goal == Decimal("1957.0")


@pytest.fixture
def zero_calorie_goal(mocker):
    """Zero calorie goal mock."""
    return mocker.patch(
        "apps.plans.models.Day._calorie_goal",
        new_callable=mocker.PropertyMock,
        return_value=Decimal("0"),
    )


def test_zero_calorie_goal(db, day, zero_calorie_goal):
    """Zero calorie goal works as expected."""
    # When
    day.save()

    # Then
    assert day.calorie_goal == 0
    assert day.calorie_intake_perc == 0
    assert day.calorie_deficit == 0
    assert day.calorie_surplus == 0
    assert day.fat_g_intake_perc == 0
    assert day.carbs_g_intake_perc == 0


def test_zero_protein_goal(db, day):
    """Zero protein goal works as expected."""
    # When
    day.protein_g_goal = 0

    # Then
    assert day._protein_g_intake_perc == 0  # pylint: disable=protected-access


def test_zero_calorie_deficit(db, day):
    """Zero calorie deficit works as expected."""
    # When
    day.calorie_goal = 1
    day.calories = 2

    # Then
    assert day.calorie_deficit == 0
