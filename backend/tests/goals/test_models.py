"""apps.goals.models tests."""

from apps.measurements.models import Measurement


def test_no_measurement(db, fat_perc_goal):
    """Goal with no measurement works as expected."""
    assert fat_perc_goal.get_weeks_to_goal(100) == 0


def test_weight_only_measurement_without_body_fat_has_no_goal_projection(
    db, fat_perc_goal
):
    """A goal projection waits until body fat has been recorded once."""
    Measurement.objects.create(
        user=fat_perc_goal.user,
        weight=80,
        body_fat_perc=None,
    )

    assert fat_perc_goal.get_weeks_to_goal(100) == 0


def test_weight_only_measurement_reuses_latest_body_fat_for_goal_projection(
    db, fat_perc_goal
):
    """Goal calculations combine the latest weight and body-fat readings."""
    Measurement.objects.create(
        user=fat_perc_goal.user,
        weight=80,
        body_fat_perc=20,
    )
    expected = fat_perc_goal.get_weeks_to_goal(100)
    Measurement.objects.create(
        user=fat_perc_goal.user,
        weight=80,
        body_fat_perc=None,
    )

    assert fat_perc_goal.get_weeks_to_goal(100) == expected
