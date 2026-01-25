"""Garmin schema tests."""

from typing import Any

import pytest

from apps.garmin.models import GarminCredential
from apps.users.models import User
from config.schema import schema


@pytest.mark.django_db
# pylint: disable=too-few-public-methods
class TestGarminSchema:
    """Garmin schema tests class."""

    class Context:
        """Context mock for GraphQL."""

        def __init__(self, request: Any) -> None:
            """Initialize context with request.

            Args:
                request (Any): request instance.
            """
            self.request = request

    @pytest.fixture
    def user(self) -> User:
        """User fixture.

        Returns:
            User: user instance.
        """
        return User.objects.create_user(
            email="test@example.com",
            password="password",
            first_name="Test",
            last_name="User",
            date_of_birth="1990-01-01",
            height=180,
        )

    def test_garmin_connection_status_false(self) -> None:
        """Test status when not connected."""
        # Given a query
        query = """
            query {
                garminConnectionStatus
            }
        """

        # When executing (unauthenticated)
        # pylint: disable=too-few-public-methods
        class Request:
            """Request mock."""

            user = type("AnonymousUser", (), {"is_authenticated": False})()

        # Use Context object
        result = schema.execute_sync(
            query, context_value=self.Context(Request())
        )

        # Then it returns False
        assert result.data["garminConnectionStatus"] is False

    def test_garmin_connection_status_true(self, user: User) -> None:
        """Test status when connected.

        Args:
            user (User): user instance.
        """
        # Given a connected user
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )

        # When executing
        request = type("Request", (), {"user": user})()

        query = """
            query {
                garminConnectionStatus
            }
        """
        result = schema.execute_sync(
            query, context_value=self.Context(request)
        )

        # Then it returns True
        assert result.data["garminConnectionStatus"] is True

    def test_connect_garmin_url_unauth(self) -> None:
        """Test connect url unauthenticated (Given unauth user)."""

        class Request:
            """Request mock."""

            user = type("AnonymousUser", (), {"is_authenticated": False})()

        query = """
            mutation {
                connectGarminUrl(redirectUri: "foo")
            }
        """
        # When executing
        result = schema.execute_sync(
            query, context_value=self.Context(Request())
        )

        # Then it raises error
        assert result.errors
        assert "Authentication required" in str(result.errors[0])

    def test_connect_garmin_url(self, user: User, settings: Any) -> None:
        """Test connect url.

        Args:
            user (User): user instance.
            settings (Any): Django settings.
        """
        # Given auth user
        settings.DEBUG = True
        request = type("Request", (), {"user": user})()

        query = """
            mutation {
                connectGarminUrl(redirectUri: "http://foo")
            }
        """

        # When executing
        result = schema.execute_sync(
            query, context_value=self.Context(request)
        )

        # Then URL is returned
        assert result.data
        assert "redirect_uri=" in result.data["connectGarminUrl"]

    @pytest.mark.asyncio
    async def test_garmin_auth_callback_unauth(self) -> None:
        """Test auth callback unauthenticated (Given unauth user)."""

        class Request:
            """Request mock."""

            user = type("AnonymousUser", (), {"is_authenticated": False})()

        query = """
            mutation {
                garminAuthCallback(code: "test")
            }
        """
        # When executing
        result = await schema.execute(
            query, context_value=self.Context(Request())
        )

        # Then it raises error
        assert result.errors
        assert "Authentication required" in str(result.errors[0])

    @pytest.mark.asyncio
    async def test_garmin_auth_callback(
        self, user: User, settings: Any
    ) -> None:
        """Test auth callback.

        Args:
            user (User): user instance.
            settings (Any): Django settings.
        """
        # Given auth user and valid code (mocked service via DEBUG=True)
        settings.DEBUG = True
        request = type("Request", (), {"user": user})()

        query = """
            mutation {
                garminAuthCallback(code: "test")
            }
        """

        # When executing
        # Using execute because mutation is async
        result = await schema.execute(
            query, context_value=self.Context(request)
        )

        # Then success and credential created
        assert result.data
        assert result.data["garminAuthCallback"] is True

        cred = await GarminCredential.objects.aget(user=user)
        assert cred.access_token == "dummy_access_token"

    @pytest.mark.asyncio
    async def test_disconnect_garmin_unauth(self) -> None:
        """Test disconnect unauthenticated (Given unauth user)."""

        class Request:
            """Request mock."""

            user = type("AnonymousUser", (), {"is_authenticated": False})()

        query = """
            mutation {
                disconnectGarmin
            }
        """
        # When executing
        result = await schema.execute(
            query, context_value=self.Context(Request())
        )

        # Then it raises error
        assert result.errors
        assert "Authentication required" in str(result.errors[0])

    @pytest.mark.asyncio
    async def test_disconnect_garmin(self, user: User) -> None:
        """Test disconnect.

        Args:
            user (User): user instance.
        """
        # Given connected user
        await GarminCredential.objects.acreate(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        request = type("Request", (), {"user": user})()

        query = """
            mutation {
                disconnectGarmin
            }
        """

        # When executing
        result = await schema.execute(
            query, context_value=self.Context(request)
        )

        # Then success and credential deleted
        assert result.data["disconnectGarmin"] is True
        assert not await GarminCredential.objects.filter(user=user).aexists()

    @pytest.mark.asyncio
    async def test_disconnect_garmin_not_connected(self, user: User) -> None:
        """Test disconnect when not connected.

        Args:
            user (User): user instance.
        """
        # Given user NOT connected
        request = type("Request", (), {"user": user})()

        query = """
            mutation {
                disconnectGarmin
            }
        """

        # When executing
        result = await schema.execute(
            query, context_value=self.Context(request)
        )

        # Then it returns False
        assert result.data["disconnectGarmin"] is False
