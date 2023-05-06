"""exercises app admin config module."""


from django.contrib import admin

from .models import DaySteps, Exercise


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """ExerciseAdmin class."""

    list_display = [
        "id",
        "user",
        "date_time",
        "type",
        "kcals",
        "duration",
        "distance",
    ]


@admin.register(DaySteps)
class DayStepsAdmin(admin.ModelAdmin):
    """DayStepsAdmin class."""

    list_display = [
        "id",
        "user",
        "day",
        "steps",
    ]
