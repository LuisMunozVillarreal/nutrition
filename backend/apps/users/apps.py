"""users app config module."""


from django.apps import AppConfig


class UsersConfig(AppConfig):
    """UsersConfig class."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
