"""plans app config module."""

from django.apps import AppConfig


class PlansConfig(AppConfig):
    """PlansConfig class."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.plans"

    def ready(self) -> None:
        """Ready App."""
        # pylint: disable=import-outside-toplevel, unused-import
        import apps.plans.signals.handlers  # noqa
