"""Garmin schema tests."""

import pytest
import strawberry
from django.conf import settings
from apps.users.models import User
from apps.garmin.models import GarminCredential
from config.schema import schema

@pytest.mark.django_db
class TestGarminSchema:
    
    class Context:
        def __init__(self, request):
            self.request = request

    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            email="test@example.com", password="password",
            first_name="Test", last_name="User",
            date_of_birth="1990-01-01", height=180
        )

    def test_garmin_connection_status_false(self):
        """Test status when not connected."""
        # Given a query
        query = """
            query {
                garminConnectionStatus
            }
        """
        
        # When executing (unauthenticated)
        class Request:
            user = getattr(User, "AnonymousUser", None) or type("AnonymousUser", (), {"is_authenticated": False})()
        
        # Use Context object
        result = schema.execute_sync(query, context_value=self.Context(Request()))
        
        # Then it returns False
        assert result.data["garminConnectionStatus"] is False

    def test_garmin_connection_status_true(self, user):
        """Test status when connected."""
        # Given a connected user
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        
        # When executing
        class Request:
            pass
        req = Request()
        req.user = user
        
        query = """
            query {
                garminConnectionStatus
            }
        """
        result = schema.execute_sync(query, context_value=self.Context(req))
        
        # Then it returns True
        assert result.data["garminConnectionStatus"] is True

    def test_connect_garmin_url_unauth(self):
        """Test connect url unauthenticated."""
        # Given unauth user
        class Request:
            user = type("AnonymousUser", (), {"is_authenticated": False})()
        
        query = """
            mutation {
                connectGarminUrl(redirectUri: "foo")
            }
        """
        # When executing
        result = schema.execute_sync(query, context_value=self.Context(Request()))
        
        # Then it raises error
        assert result.errors
        assert "Authentication required" in str(result.errors[0])

    def test_connect_garmin_url(self, user, settings):
        """Test connect url."""
        # Given auth user
        settings.DEBUG = True
        
        class Request:
            pass
        req = Request()
        req.user = user
        
        query = """
            mutation {
                connectGarminUrl(redirectUri: "http://foo")
            }
        """
        
        # When executing
        result = schema.execute_sync(query, context_value=self.Context(req))
        
        # Then URL is returned
        assert result.data
        assert "redirect_uri=" in result.data["connectGarminUrl"]

    @pytest.mark.asyncio
    async def test_garmin_auth_callback(self, user, settings):
        """Test auth callback."""
        # Given auth user and valid code (mocked service via DEBUG=True)
        settings.DEBUG = True
        
        class Request:
            pass
        req = Request()
        req.user = user
        
        query = """
            mutation {
                garminAuthCallback(code: "test")
            }
        """
        
        # When executing
        # Using execute because mutation is async
        result = await schema.execute(query, context_value=self.Context(req))
        
        # Then success and credential created
        assert result.data
        assert result.data["garminAuthCallback"] is True
        
        cred = await GarminCredential.objects.aget(user=user)
        assert cred.access_token == "dummy_access_token"

    @pytest.mark.asyncio
    async def test_disconnect_garmin(self, user):
        """Test disconnect."""
        # Given connected user
        await GarminCredential.objects.acreate(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        
        class Request:
            pass
        req = Request()
        req.user = user

        query = """
            mutation {
                disconnectGarmin
            }
        """
        
        # When executing
        result = await schema.execute(query, context_value=self.Context(req))
        
        # Then success and credential deleted
        assert result.data["disconnectGarmin"] is True
        assert not await GarminCredential.objects.filter(user=user).aexists()

    @pytest.mark.asyncio
    async def test_disconnect_garmin_not_connected(self, user):
        """Test disconnect when not connected."""
        # Given user NOT connected
        
        class Request:
            pass
        req = Request()
        req.user = user

        query = """
            mutation {
                disconnectGarmin
            }
        """
        
        # When executing
        result = await schema.execute(query, context_value=self.Context(req))
        
        # Then returns False (or whatever logic says)?
        # Implementation says: return False if hasattr check fails.
        assert result.data["disconnectGarmin"] is False
