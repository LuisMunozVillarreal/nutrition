"""food proportion tests module."""


def test_different_serving_unit(db, intake):
    """Different serving unit are calculated correctly."""
    # Given
    intake.food.serving_unit = "mg"
    intake.food.save()
    intake.food.refresh_from_db()

    # When
    portion = intake.get_portion_for(intake.food, "protein_g")

    # Then
    assert portion == 25000
