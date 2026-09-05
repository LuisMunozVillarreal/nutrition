"""exercises app admin config module."""

# Permission hooks retain Django's callback signatures even though every path
# deliberately returns False.
# pylint: disable=missing-param-doc,missing-return-doc,unused-argument

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

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

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Prevent writes that bypass canonical aggregate locks."""
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: DaySteps | None = None
    ) -> bool:
        """Keep imported provenance consistent by making rows view-only."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: DaySteps | None = None
    ) -> bool:
        """Require deletes to pass through the owner-scoped service."""
        return False


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
    extra = 0
    show_change_link = False
    can_delete = False

    fields = [
        "steps",
        "kcals",
    ]

    readonly_fields = ["steps", "kcals"]

    def has_add_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        """Prevent inline creation outside the canonical service."""
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        """Prevent inline edits from retaining stale provenance."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        """Prevent inline deletes with inverted lock ordering."""
        return False
