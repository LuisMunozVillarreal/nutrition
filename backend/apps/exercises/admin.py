"""exercises app admin config module."""

from django.contrib import admin

from apps.libs.admin import round_field

from .models import DaySteps, Exercise


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """ExerciseAdmin class."""

    list_display = [
        "id",
        "day_time",
        "type",
        "kcals",
        "duration",
        round_field("distance"),
    ]


@admin.register(DaySteps)
class DayStepsAdmin(admin.ModelAdmin):
    """DayStepsAdmin class."""

    list_display = [
        "id",
        "day",
        "steps",
    ]


class ExerciseInlineBase:
    """Exercise inline class."""

    # pylint: disable=too-few-public-methods

    model = Exercise
    extra = 0
    show_change_link = True

    fields = [
        "type",
        "kcals",
        "duration",
        "distance",
    ]


class DayStepsInlineBase:
    """DaySteps inline class."""

    # pylint: disable=too-few-public-methods

    model = DaySteps
    show_change_link = True

    fields = [
        "steps",
        "kcals",
    ]

    readonly_fields = [
        "kcals",
    ]
