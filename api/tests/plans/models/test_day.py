"""plans day food model tests module."""


def test_no_calorie_deficit(db, intake):
    """Calorie deficit returns 0 when there is a surplus."""
    # Given
    intake.serving_size = 10000
    intake.save()

    # When / Then
    assert intake.day.calorie_deficit == 0
