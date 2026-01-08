"""Garmin service module."""

import urllib.parse
from typing import Any, Dict, List

from django.conf import settings


class GarminService:
    """Garmin Service class."""

    OAUTH_URL = "https://connect.garmin.com/oauthConfirm"
    TOKEN_URL = (
        "https://connectapi.garmin.com/oauth-service/oauth/token"  # nosec B105
    )

    # Real Garmin Connect API endpoints would be different.
    # Usually requiring signing.
    # Given requirements, I will implement a standard OAuth2 structure.

    def __init__(self) -> None:
        """Initialize service with credentials."""
        self.client_id = settings.GARMIN_CLIENT_ID
        self.client_secret = settings.GARMIN_CLIENT_SECRET

    def get_authorization_url(self, redirect_uri: str) -> str:
        """Get authorization URL.

        Args:
            redirect_uri (str): URI to redirect after auth.

        Returns:
            str: Garmin authorization URL.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "activity",
        }
        if getattr(settings, "MOCK_GARMIN", False):
            return f"{redirect_uri}?code=testcode"
        return f"{self.OAUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange code for token.

        Args:
            code (str): authorization code.
            redirect_uri (str): URI used during auth.

        Returns:
            Dict[str, Any]: OAuth 2.0 token response.

        Raises:
            NotImplementedError: if not in DEBUG mode.
        """
        # pylint: disable=unused-argument
        if settings.DEBUG or getattr(settings, "MOCK_GARMIN", False):
            # Simulation for development/testing
            return {
                "access_token": "dummy_access_token",
                "refresh_token": "dummy_refresh_token",
                "expires_in": 3600,
                "garmin_user_id": "dummy_user_id",
            }

        raise NotImplementedError(
            "Real Garmin API call not yet fully configured"
        )

    def fetch_activities(
        self, access_token: str, start_date: Any, end_date: Any
    ) -> List[Dict[str, Any]]:
        """Fetch activities.

        Args:
            access_token (str): access token.
            start_date (Any): start date for query.
            end_date (Any): end date for query.

        Returns:
            List[Dict[str, Any]]: list of activities.
        """
        # pylint: disable=unused-argument
        if settings.DEBUG or getattr(settings, "MOCK_GARMIN", False):
            return [
                {
                    "activityId": 123456789,
                    "activityName": "Morning Ride",
                    "startTimeLocal": "2023-10-27 08:00:00",
                    "type": "cycling",
                    "distance": 20000.0,
                    "duration": 3600.0,
                    "calories": 500,
                }
            ]

        return []
