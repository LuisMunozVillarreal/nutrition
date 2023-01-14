"""users app model tests module."""


def test_no_last_name(db, user):
    """Show user with no last name correctly."""
    # Given
    user.last_name = ""
    user.save()

    # When
    name = user.full_name

    # Then
    assert "first_name" in name
    assert " " not in name
