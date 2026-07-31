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
        "started_at",
        "kcals",
        "duration_seconds",
        "distance",
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
    ]
    readonly_fields = ["connection", "provider_activity_id", "provider_activity_type"]
