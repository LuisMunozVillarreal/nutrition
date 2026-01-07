"""Garmin admin module."""

from django.contrib import admin

from .models import GarminCredential


@admin.register(GarminCredential)
class GarminCredentialAdmin(admin.ModelAdmin):
    """Garmin credential admin."""

    list_display = ("user", "garmin_user_id", "created_at")
    search_fields = ("user__email", "garmin_user_id")
    readonly_fields = ("created_at", "updated_at")
