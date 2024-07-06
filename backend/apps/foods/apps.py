"""foods app config module."""

from django.apps import AppConfig


class FoodsConfig(AppConfig):
    """FoodsConfig class."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.foods"

    def ready(self) -> None:
        """Ready App."""
        # pylint: disable=import-outside-toplevel, unused-import
        import apps.foods.signals.handlers  # noqa
