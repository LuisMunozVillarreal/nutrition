"""plans day food model tests module."""


def test_no_calorie_deficit(db, day_food):
    """Calorie deficit returns 0 when there is a surplus."""
    # Given
    day_food.serving_size = 10000
    day_food.save()

    # When / Then
    assert day_food.day.calorie_deficit == 0
