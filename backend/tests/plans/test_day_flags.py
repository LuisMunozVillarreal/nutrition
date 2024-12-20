"""Tests for the day flags."""

from apps.plans.models import Intake


def test_new_day_all_flags_off(day):
    """New day has all flags off."""
    assert not day.breakfast_flag
    assert not day.lunch_flag
    assert not day.snack_flag
    assert not day.dinner_flag
    assert not day.exercises_flag
    assert not day.steps_flag
    assert not day.completed


def test_day_with_all_exc(day_factory):
    """A day"with all exc flags on will make on flags on."""
    # When a day has all exc flags on
    day = day_factory(
        breakfast_exc=True,
        lunch_exc=True,
        snack_exc=True,
        dinner_exc=True,
        exercises_exc=True,
        steps_exc=True,
    )

    # Then all day flags are on
    assert day.breakfast_flag
    assert day.lunch_flag
    assert day.snack_flag
    assert day.dinner_flag
    assert day.exercises_flag
    assert day.steps_flag
    assert day.completed


def test_breakfast_intake_flag_on(intake_factory):
    """A day with a breakfast intake will have the breakfast flag on."""
    # When a day has a breakfast intake
    intake = intake_factory(meal=Intake.MEAL_BREAKFAST)

    # Then the day's breakfast flag is on
    assert intake.day.breakfast_flag


def test_non_processed_breakfast_intake_flag_off(intake_factory):
    """Non-processed breakfast intakes doesn't get the  breakfast flag on."""
    # When a day has a non-processed breakfast intake
    intake = intake_factory(meal=Intake.MEAL_BREAKFAST, food=None)

    # Then the day's breakfast flag is on
    assert not intake.day.breakfast_flag


def test_delete_breakfast_intake(intake_factory):
    """Deleting a breakfast intake will turn off the breakfast flag."""
    # Given a day with a breakfast intake
    intake = intake_factory(meal=Intake.MEAL_BREAKFAST)

    # And the day's breakfast flag is on
    assert intake.day.breakfast_flag

    # When the intake is deleted
    intake.delete()

    # Then the day's breakfast flag is off
    intake.day.refresh_from_db()
    assert not intake.day.breakfast_flag


def test_exercise_flag(exercise_factory):
    """A day with an exercise will have the exercise flag on."""
    # When a day has an exercise
    exercise = exercise_factory()

    # Then the day's exercise flag is on
    assert exercise.day.exercises_flag


def test_delete_exercise(exercise_factory):
    """Deleting an exercise will turn off the exercise flag."""
    # Given a day with an exercise
    exercise = exercise_factory()

    # And the day's exercise flag is on
    assert exercise.day.exercises_flag

    # When the exercise is deleted
    exercise.delete()

    # Then the day's exercise flag is off
    exercise.day.refresh_from_db()
    assert not exercise.day.exercises_flag


def test_steps_flag(day_steps_factory):
    """A day with steps will have the steps flag on."""
    # When a day has steps
    steps = day_steps_factory()

    # Then the day's steps flag is on
    assert steps.day.steps_flag


def test_delete_steps(day_steps_factory):
    """Deleting steps will turn off the steps flag."""
    # Given a day with steps
    day_steps = day_steps_factory()
    day = day_steps.day

    # And the day's steps flag is on
    assert day.steps_flag

    # When the steps are deleted
    day_steps.delete()

    # Then the day's steps flag is off
    assert not day.steps_flag
