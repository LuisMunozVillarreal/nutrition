"""apps.goals.models tests."""


def test_no_measurement(db, fat_perc_goal):
    """Goal with no measurement works as expected."""
    assert fat_perc_goal.get_weeks_to_goal(100) == 0
