"""Garmin service tests."""

from typing import Any

import pytest
from django.conf import settings

from apps.garmin.service import GarminService


@pytest.fixture
def garmin_service() -> GarminService:
    """Garmin service fixture.

    Returns:
        GarminService: service instance.
    """
    return GarminService()


def test_get_authorization_url(garmin_service: GarminService) -> None:
    """Test generation of auth URL.

    Args:
        garmin_service (GarminService): garmin service.
    """
    # Given a redirect URI
    redirect_uri = "http://localhost/callback"

    # When generating auth URL
    url = garmin_service.get_authorization_url(redirect_uri)

    # Then it contains client_id and redirect_uri
    assert settings.GARMIN_CLIENT_ID in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%2Fcallback" in url
    assert "response_type=code" in url


def test_exchange_code_mock(
    garmin_service: GarminService, mocker: Any
) -> None:
    """Test exchange_code with mock.

    Args:
        garmin_service (GarminService): garmin service.
        mocker (Any): pytest-mock mocker.
    """
    # Given DEBUG settings is True
    mocker.patch.object(settings, "DEBUG", True)

    # When exchanging code
    result = garmin_service.exchange_code("test_code", "uri")

    # Then dummy data is returned
    assert result["access_token"] == "dummy_access_token"
    assert result["garmin_user_id"] == "dummy_user_id"


def test_exchange_code_real_not_implemented(
    garmin_service: GarminService, mocker: Any
) -> None:
    """Test exchange_code real implementation raises error.

    Args:
        garmin_service (GarminService): garmin service.
        mocker (Any): pytest-mock mocker.
    """
    # Given DEBUG is False
    mocker.patch.object(settings, "DEBUG", False)

    # When exchanging code
    # Then NotImplementedError is raised
    with pytest.raises(NotImplementedError):
        garmin_service.exchange_code("test_code", "uri")


def test_fetch_activities_mock(
    garmin_service: GarminService, mocker: Any
) -> None:
    """Test fetch_activities with mock.

    Args:
        garmin_service (GarminService): garmin service.
        mocker (Any): pytest-mock mocker.
    """
    # Given DEBUG settings is True
    mocker.patch.object(settings, "DEBUG", True)

    # When fetching activities
    activities = garmin_service.fetch_activities("token", "start", "end")

    # Then dummy activity is returned
    assert len(activities) == 1
    assert activities[0]["activityName"] == "Morning Ride"


def test_fetch_activities_real(
    garmin_service: GarminService, mocker: Any
) -> None:
    """Test fetch_activities real implementation (empty).

    Args:
        garmin_service (GarminService): garmin service.
        mocker (Any): pytest-mock mocker.
    """
    # Given DEBUG is False
    mocker.patch.object(settings, "DEBUG", False)

    # When fetching activities
    activities = garmin_service.fetch_activities("token", "start", "end")

    # Then empty list is returned
    assert not activities
