"""plan day tests module."""

from decimal import Decimal

import pytest

from config.settings import CARB_KCAL_GRAM, FAT_KCAL_GRAM, PROTEIN_KCAL_GRAM


def test_energy_goal_meets_macros(db, day):
    """Energy goal meets macros."""
    assert (
        day.energy_kcal_goal
        == day.protein_g_goal * PROTEIN_KCAL_GRAM
        + day.fat_g_goal * FAT_KCAL_GRAM
        + day.carbs_g_goal * CARB_KCAL_GRAM
    )


def test_protein_g_goal(db, day):
    """Protein goal is correct."""
    assert day.protein_g_goal == Decimal("235.75")


def test_estimated_energy_goal(db, day):
    """Estimated energy goal is correct."""
    # Given
    day.tracked = False
    day.save()

    # When / Then
    assert day.energy_kcal_goal == Decimal("2501.3109")


def test_estimated_fat_g_goal(db, day):
    """Estimated fat goal is correct."""
    # Given
    day.tracked = False
    day.save()

    # When / Then
    assert day.fat_g_goal == Decimal("69.48085833333333333333333333")


def test_estimated_carb_g_goal(db, day):
    """Estimated carb goal is correct."""
    # Given
    day.tracked = False
    day.save()

    # When / Then
    assert day.carbs_g_goal == Decimal("233.24579375")


def test_tracked_energy_goal(db, day_steps, exercise):
    """Tracked energy goal is correct."""
    assert day_steps.day.energy_kcal_goal == Decimal("1889.1352")


def test_tracked_energy_goal_no_steps(db, day, exercise):
    """Tracked energy goal with no steps is correct."""
    assert day.energy_kcal_goal == Decimal("1859.1352")


def test_increase_day_nutrients(db, intake):
    """Calculate a increase in day nutrients correctly."""
    # When
    intake.num_servings = 2
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
    assert day.energy_kcal_goal == Decimal("1859.1352")

    # When
    exercise.delete()

    # Then
    day.refresh_from_db()
    assert day.energy_kcal_goal == Decimal("1759.14")


@pytest.fixture
def zero_energy_kcal_goal(mocker):
    """Zero energy kcal goal mock."""
    return mocker.patch(
        "apps.plans.models.Day._energy_kcal_goal",
        new_callable=mocker.PropertyMock,
        return_value=Decimal("0"),
    )


def test_zero_energy_goal(db, day, zero_energy_kcal_goal):
    """Zero energy kcal goal works as expected."""
    # When
    day.save()

    # Then
    assert day.energy_kcal_goal == 0
    assert day.energy_kcal_intake_perc == 0
    assert day.energy_kcal_goal_diff == 0
    assert day.fat_g_intake_perc == 0
    assert day.carbs_g_intake_perc == 0


def test_zero_protein_goal(db, day):
    """Zero protein goal works as expected."""
    # When
    day.protein_g_goal = 0

    # Then
    assert day._protein_g_intake_perc == 0  # pylint: disable=protected-access
