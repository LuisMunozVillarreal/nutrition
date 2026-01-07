"""Garmin models tests."""

from apps.garmin.models import GarminCredential
from apps.users.models import User
import pytest


@pytest.mark.django_db
def test_garmin_credential_str() -> None:
    """Test GarminCredential string representation."""
    # Given a user
    user = User.objects.create_user(
        email="test@example.com", password="password",
        first_name="Test", last_name="User",
        date_of_birth="1990-01-01", height=180
    )

    # And a credential
    cred = GarminCredential.objects.create(
        user=user,
        access_token="token",
        refresh_token="refresh",
        expires_at=1234567890
    )

    # When getting string representation
    result = str(cred)

    # Then it matches expected format
    assert result == f"Garmin Credential for {user}"
