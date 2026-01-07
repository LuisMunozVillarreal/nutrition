"""Garmin service tests."""

from django.conf import settings
from apps.garmin.service import GarminService
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def service():
    return GarminService()

def test_get_authorization_url(service) -> None:
    """Test generation of auth URL."""
    # Given a redirect URI
    redirect_uri = "http://localhost/callback"
    
    # When generating auth URL
    url = service.get_authorization_url(redirect_uri)
    
    # Then it contains client_id and redirect_uri
    assert settings.GARMIN_CLIENT_ID in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%2Fcallback" in url
    assert "response_type=code" in url

def test_exchange_code_mock(service, mocker) -> None:
    """Test exchange_code with mock."""
    # Given DEBUG settings is True or MOCK_GARMIN is True
    mocker.patch.object(settings, "DEBUG", True)
    
    # When exchanging code
    result = service.exchange_code("test_code", "uri")
    
    # Then dummy data is returned
    assert result["access_token"] == "dummy_access_token"
    assert result["garmin_user_id"] == "dummy_user_id"

def test_exchange_code_real_not_implemented(service, mocker) -> None:
    """Test exchange_code real implementation raises error."""
    # Given DEBUG is False and MOCK_GARMIN is False
    mocker.patch.object(settings, "DEBUG", False)
    # Ensure MOCK_GARMIN is not set (default False)
    
    # When exchanging code
    # Then NotImplementedError is raised
    with pytest.raises(NotImplementedError):
         service.exchange_code("test_code", "uri")

def test_fetch_activities_mock(service, mocker) -> None:
    """Test fetch_activities with mock."""
    # Given DEBUG settings is True
    mocker.patch.object(settings, "DEBUG", True)
    
    # When fetching activities
    activities = service.fetch_activities("token", "start", "end")
    
    # Then dummy activity is returned
    assert len(activities) == 1
    assert activities[0]["activityName"] == "Morning Ride"

def test_fetch_activities_real(service, mocker) -> None:
    """Test fetch_activities real implementation (empty)."""
    # Given DEBUG is False
    mocker.patch.object(settings, "DEBUG", False)
    
    # When fetching activities
    activities = service.fetch_activities("token", "start", "end")
    
    # Then empty list is returned
    assert activities == []
