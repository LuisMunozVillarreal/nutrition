"""Garmin app configuration."""

from django.apps import AppConfig


class GarminConfig(AppConfig):
    """Garmin app config."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.garmin"
    verbose_name = "Garmin"
