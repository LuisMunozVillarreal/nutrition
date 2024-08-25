"""Test salt conversion module."""


def test_salt_to_sodium(food):
    """Salt to sodium."""
    # When salt is changed
    food.salt_g = 1
    food.save()

    # Then sodium conversion is correct
    assert food.sodium_mg == 400


def test_sodium_to_salt(food):
    """Sodium to salt."""
    # When sodium is changed
    food.sodium_mg = 400
    food.save()

    # Then salt conversion is correct
    assert food.salt_g == 1
