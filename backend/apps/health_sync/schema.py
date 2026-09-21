"""GraphQL management surface for health-sync companion devices."""

# Strawberry signatures are the GraphQL contract; concise docstrings describe
# the authorization and exposure rules.
# pylint: disable=missing-param-doc,missing-return-doc,missing-raises-doc

from __future__ import annotations

from typing import Any

import strawberry
from django.db import transaction
from django.utils import timezone
from strawberry.types import Info

from apps.health_sync.models import (
    MAX_ACTIVE_DEVICES_PER_USER,
    PAIRING_CODE_EMISSION_INTERVAL,
    HealthSyncDevice,
    HealthSyncPairingCode,
)
from config.middleware import authenticated_request_user


def _authenticated_user(info: Info) -> Any:
    """Resolve the bearer or session principal for a GraphQL request."""
    context = info.context
    request = getattr(context, "request", context)
    user = authenticated_request_user(request)
    if user is None or not user.is_authenticated:
        raise PermissionError("Authentication required")
    return user


@strawberry.type
class HealthSyncPairingPayload:
    """One-time pairing code shown to the authenticated user."""

    code: str
    expires_at: str


@strawberry.type
class HealthSyncDeviceType:
    """Safe metadata for a paired companion device."""

    id: strawberry.ID
    name: str
    last_seen_at: str | None
    last_success_at: str | None
    expires_at: str
    created_at: str

    @staticmethod
    def from_model(device: HealthSyncDevice) -> "HealthSyncDeviceType":
        """Convert a device without exposing credential material."""
        return HealthSyncDeviceType(
            id=strawberry.ID(str(device.id)),
            name=device.name,
            last_seen_at=(
                device.last_seen_at.isoformat()
                if device.last_seen_at
                else None
            ),
            last_success_at=(
                device.last_success_at.isoformat()
                if device.last_success_at
                else None
            ),
            expires_at=device.expires_at.isoformat(),
            created_at=device.created_at.isoformat(),
        )


@strawberry.type
class HealthSyncQuery:
    """Queries for the current user's active companion devices."""

    @strawberry.field
    def health_sync_devices(self, info: Info) -> list[HealthSyncDeviceType]:
        """List non-revoked devices owned by the current user."""
        user = _authenticated_user(info)
        return [
            HealthSyncDeviceType.from_model(device)
            for device in HealthSyncDevice.objects.filter(
                user=user,
                revoked_at=None,
                expires_at__gt=timezone.now(),
            ).order_by("-created_at")[:MAX_ACTIVE_DEVICES_PER_USER]
        ]


@strawberry.type
class HealthSyncMutation:
    """Mutations for pairing and revoking companion devices."""

    @strawberry.mutation
    def create_health_sync_pairing_code(
        self,
        info: Info,
    ) -> HealthSyncPairingPayload:
        """Create a short-lived single-use code for the current user."""
        user = _authenticated_user(info)
        with transaction.atomic():
            locked_user = (
                type(user).objects.select_for_update().get(pk=user.pk)
            )
            recent_cutoff = timezone.now() - PAIRING_CODE_EMISSION_INTERVAL
            if HealthSyncPairingCode.objects.filter(
                user=locked_user,
                created_at__gte=recent_cutoff,
            ).exists():
                raise ValueError(
                    "Please wait before creating another pairing code"
                )
            now = timezone.now()
            HealthSyncPairingCode.objects.filter(
                user=locked_user,
                consumed_at=None,
            ).update(consumed_at=now, updated_at=now)
            raw_code, pairing = HealthSyncPairingCode.issue(locked_user)
        return HealthSyncPairingPayload(
            code=raw_code,
            expires_at=pairing.expires_at.isoformat(),
        )

    @strawberry.mutation
    def revoke_health_sync_device(self, info: Info, id: strawberry.ID) -> bool:
        """Revoke a device only when it belongs to the current user."""
        user = _authenticated_user(info)
        try:
            device = HealthSyncDevice.objects.get(
                pk=id,
                user=user,
                revoked_at=None,
            )
        except HealthSyncDevice.DoesNotExist:
            return False
        device.revoke()
        return True
