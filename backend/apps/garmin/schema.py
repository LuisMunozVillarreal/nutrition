"""Garmin schema module."""

import strawberry
from asgiref.sync import sync_to_async
from strawberry.types import Info

from .models import GarminCredential
from .service import GarminService


@strawberry.type
# pylint: disable=too-few-public-methods
class Query:
    """Garmin queries."""

    @strawberry.field
    def garmin_connection_status(self, info: Info) -> bool:
        """Check if user is connected to Garmin.

        Args:
            info (Info): GraphQL info object.

        Returns:
            bool: True if connected, False otherwise.
        """
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        return hasattr(user, "garmin_credential")


@strawberry.type
# pylint: disable=too-few-public-methods
class Mutation:
    """Garmin mutations."""

    @strawberry.mutation
    def connect_garmin_url(self, info: Info, redirect_uri: str) -> str:
        """Get Garmin Connect URL.

        Args:
            info (Info): GraphQL info object.
            redirect_uri (str): redirection URI.

        Returns:
            str: Garmin authorization URL.

        Raises:
            Exception: if user is not authenticated.
        """
        user = info.context.request.user
        if not user.is_authenticated:
            # pylint: disable=broad-exception-raised
            raise Exception("Authentication required")

        service = GarminService()
        return service.get_authorization_url(redirect_uri)

    @strawberry.mutation
    async def garmin_auth_callback(self, info: Info, code: str) -> bool:
        """Handle Garmin Auth Callback.

        Args:
            info (Info): GraphQL info object.
            code (str): authorization code.

        Returns:
            bool: True if success.

        Raises:
            Exception: if user is not authenticated.
        """
        user = info.context.request.user

        if not user.is_authenticated:
            # pylint: disable=broad-exception-raised
            raise Exception("Authentication required")

        service = GarminService()
        token_data = service.exchange_code(code, redirect_uri="")

        await sync_to_async(GarminCredential.objects.update_or_create)(
            user=user,
            defaults={
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", ""),
                "expires_at": 0,
                "garmin_user_id": token_data.get("garmin_user_id"),
            },
        )
        
        # Trigger sync immediately
        from apps.garmin.sync import sync_activities
        await sync_to_async(sync_activities)(user)
        
        return True

    @strawberry.mutation
    async def disconnect_garmin(self, info: Info) -> bool:
        """Disconnect Garmin account.

        Args:
            info (Info): GraphQL info object.

        Returns:
            bool: True if success.

        Raises:
            Exception: if user is not authenticated.
        """
        user = info.context.request.user
        if not user.is_authenticated:
            # pylint: disable=broad-exception-raised
            raise Exception("Authentication required")

        count, _ = await GarminCredential.objects.filter(user=user).adelete()
        return count > 0
