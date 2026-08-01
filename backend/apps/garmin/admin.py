"""Garmin admin configuration module."""

from django.contrib import admin

from .models import GarminActivity, GarminConnection


@admin.register(GarminConnection)
class GarminConnectionAdmin(admin.ModelAdmin):
    """Admin registration without exposing token payloads."""

    list_display = [
        "id",
        "user",
        "provider",
        "provider_account_id",
        "is_connected",
        "last_synced_at",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "access_token_expires_at",
        "last_synced_at",
        "last_sync_summary",
    ]

    fields = [
        "user",
        "provider",
        "provider_account_id",
        "provider_scopes",
        "access_token_expires_at",
        "last_synced_at",
        "last_sync_summary",
    ]


@admin.register(GarminActivity)
class GarminActivityAdmin(admin.ModelAdmin):
    """Admin view for imported activity provenance."""

    list_display = [
        "id",
        "connection",
        "provider_activity_id",
        "provider_activity_type",
        "provider_account_id",
        "pending_reconciliation",
        "started_at",
        "kcals",
        "duration_seconds",
        "distance",
    ]
    readonly_fields = [
        "connection",
        "provider_activity_id",
        "provider_activity_type",
        "provider_account_id",
        "provider_local_started_date",
        "provider_local_started_time",
        "provider_timezone_offset_minutes",
        "day",
        "exercise",
        "started_at",
        "kcals",
        "duration_seconds",
        "distance",
        "pending_reconciliation",
    ]
    fields = [
        "connection",
        "provider_activity_id",
        "provider_activity_type",
        "provider_account_id",
        "day",
        "exercise",
        "started_at",
        "kcals",
        "duration_seconds",
        "distance",
        "provider_timezone_offset_minutes",
        "provider_local_started_date",
        "provider_local_started_time",
        "pending_reconciliation",
    ]

    def has_add_permission(self, request):  # type: ignore[override]
        """Disallow creating provenance records in the admin."""
        return False

    def has_change_permission(
        self, request, obj=None  # type: ignore[override]
    ):
        """Disallow changing provenance records in the admin."""
        return False

    def has_delete_permission(
        self, request, obj=None  # type: ignore[override]
    ):
        """Disallow deleting provenance records in the admin."""
        return False
