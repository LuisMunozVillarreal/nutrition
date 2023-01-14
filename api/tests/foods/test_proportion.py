"""food proportion tests module."""


def test_different_serving_unit(db, day_food):
    """Different serving unit are calculated correctly."""
    # Given
    day_food.food.serving_unit = "mg"
    day_food.food.save()
    day_food.food.refresh_from_db()

    # When
    portion = day_food.get_portion_for(day_food.food, "protein_g")

    # Then
    assert portion == 25000
