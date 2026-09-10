"""Health sync Django application."""

from django.apps import AppConfig


class HealthSyncConfig(AppConfig):
    """Configure scoped companion-device synchronization."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health_sync"
    verbose_name = "Health sync"
