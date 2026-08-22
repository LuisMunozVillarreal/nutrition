"""Garmin app config module."""

from django.apps import AppConfig


class GarminConfig(AppConfig):
    """GarminConfig class."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.garmin"
