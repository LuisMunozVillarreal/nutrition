"""exercises app config module."""


from django.apps import AppConfig


class ExercisesConfig(AppConfig):
    """ExercisesConfig class."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exercises"
