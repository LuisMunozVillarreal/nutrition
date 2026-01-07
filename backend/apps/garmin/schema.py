"""Garmin schema module."""

import strawberry
from asgiref.sync import sync_to_async
from django.conf import settings
from strawberry.types import Info
from .models import GarminCredential
from .service import GarminService

@strawberry.type
class Query:
    """Garmin queries."""

    @strawberry.field
    def garmin_connection_status(self, info: Info) -> bool:
        """Check if user is connected to Garmin."""
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        return hasattr(user, "garmin_credential")

@strawberry.type
class Mutation:
    """Garmin mutations."""

    @strawberry.mutation
    def connect_garmin_url(self, info: Info, redirect_uri: str) -> str:
        """Get Garmin Connect URL."""
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        
        service = GarminService()
        return service.get_authorization_url(redirect_uri)

    @strawberry.mutation
    async def garmin_auth_callback(self, info: Info, code: str) -> bool:
        """Handle Garmin Auth Callback."""
        user = info.context.request.user
        # In AsyncGraphQLView, user might be lazy or need proper handling?
        # Standard Strawberry Django Auth should handle it?
        # If user is not authenticated, we can't save.
        # Note: request.user access might be sync?
        
        if not user.is_authenticated:
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
            }
        )
        return True

    @strawberry.mutation
    async def disconnect_garmin(self, info: Info) -> bool:
        """Disconnect Garmin account."""
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")

        count, _ = await GarminCredential.objects.filter(user=user).adelete()
        return count > 0
