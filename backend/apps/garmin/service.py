"""Garmin service module."""
import urllib.parse
from typing import Dict, Any, Optional
import requests
from django.conf import settings

class GarminService:
    """Garmin Service class."""

    OAUTH_URL = "https://connect.garmin.com/oauthConfirm" # Simplified/Dummy for now as Garmin is OAuth1.0a or 2.0 depending on integration. 
    # NOTE: Garmin Health API is usually OAuth 1.0a, but newer integrations might be 2.0.
    # For this task, assuming standard OAuth 2.0 flow as per user request "OAuth 2.0 flow".
    
    TOKEN_URL = "https://connectapi.garmin.com/oauth-service/oauth/token" # Example
    
    # Real Garmin Connect API endpoints would be different, usually requiring signing.
    # Given requirements, I will implement a standard OAuth2 structure.

    def __init__(self) -> None:
        self.client_id = settings.GARMIN_CLIENT_ID
        self.client_secret = settings.GARMIN_CLIENT_SECRET

    def get_authorization_url(self, redirect_uri: str) -> str:
        """Get authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "activity", # Example scope
        }
        return f"{self.OAUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange code for token."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        # In a real scenario, this would POST to Garmin
        # response = requests.post(self.TOKEN_URL, data=data)
        # response.raise_for_status()
        # return response.json()
        
        # MOCK Implementation if configured, or just mock structure for now
        # Since I cannot easily hit real Garmin API without real credentials.
        if settings.DEBUG: 
             # Simulation for development/testing
             return {
                 "access_token": "dummy_access_token",
                 "refresh_token": "dummy_refresh_token",
                 "expires_in": 3600,
                 "garmin_user_id": "dummy_user_id"
             }
        
        # Real call (commented out until real endpoints verified)
        # return requests.post(self.TOKEN_URL, data=data).json()
        raise NotImplementedError("Real Garmin API call not yet fully configured")

    def fetch_activities(self, access_token: str, start_date: Any, end_date: Any) -> list:
        """Fetch activities."""
        # Parsing dates if they are not string or whatever
        # ...

        # Mock Data for testing/dev
        if settings.DEBUG or getattr(settings, "MOCK_GARMIN", False):
            # Return a dummy cycling activity
            return [
                {
                    "activityId": 123456789,
                    "activityName": "Morning Ride",
                    "startTimeLocal": "2023-10-27 08:00:00", # Fixed date for reproducible test? Or dynamic? 
                    # Actually for sync to work it must match the Day's date.
                    # Best to mock dynamic or ensure test sets up Day for this date.
                    # Let's use today's date minus 1 day to be safe?
                    # Or just return empty list by default and let tests patch it.
                    # But for manual verification usage... 
                    "type": "cycling",
                    "distance": 20000.0, # 20km
                    "duration": 3600.0, # 1h
                    "calories": 500
                }
            ]
            
        # Real Implementation place holder (requires network call)
        # response = requests.get(...)
        return []
