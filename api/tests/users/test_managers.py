"""apps.users.managers tests."""


import pytest
from django.contrib.auth import get_user_model


def test_no_email(db):
    """Users with no email can't be created."""
    with pytest.raises(ValueError):
        get_user_model().objects.create_user(
            None, None, date_of_birth="1985-9-12"
        )


def test_create_user_icase_email(db):
    """User's email is icase sensitive."""
    user = get_user_model().objects.create_user(
        "TEST@test.com", "password", date_of_birth="1985-9-12", height=183
    )
    assert user.email == "test@test.com"
    assert user.check_password("password")


def test_create_superuser(db):
    """Superuser is created without username."""
    password_str = "password"
    user = get_user_model().objects.create_superuser(
        "test@test.com", password_str, date_of_birth="1985-9-12", height=183
    )
    assert user.is_superuser is True
    assert user.check_password(password_str)


def test_change_password_on_db(db, user):
    """Change password on db correctly."""
    user.password = "another_password"
    user.save()
    assert user.check_password("another_password")


def test_change_password_via_admin(db, user):
    """Change password via admin correctly."""
    password = "another_password"

    # The only thing the command does is this
    user.set_password(password)
    user.save()

    assert user.check_password(password)
