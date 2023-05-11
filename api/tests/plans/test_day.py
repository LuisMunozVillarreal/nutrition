"""plan day tests module."""


def test_protein_intage_g(db, intake):
    """Calculate protein intake in grams correctly."""
    assert intake.day.protein_intake_g == 25


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
