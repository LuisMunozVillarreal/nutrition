"""plan day tracking tests module."""


def test_protein_intage_g(db, day_food):
    """Calculate protein intake in grams correctly."""
    assert day_food.day.protein_intake_g == 25


def test_decrease_day_tracking_nutrients(db, day_food):
    """Calculate a decrease in day tracking nutrients correctly."""
    # Given
    day_tracking = day_food.day
    assert day_tracking.protein_g == 25

    # When
    day_food.delete()

    # Then
    day_tracking.refresh_from_db()
    assert day_tracking.protein_g == 0
