"""goals app config module."""


from django.apps import AppConfig


class GoalsConfig(AppConfig):
    """GoalConfig class."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.goals"
