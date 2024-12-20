"""week admin config module."""

import copy
import datetime
from typing import Any, Dict

from django.contrib import admin
from django.http import HttpRequest

# pylint: disable=no-name-in-module
from nested_admin import (  # type: ignore[import]
    NestedModelAdmin,
    NestedTabularInline,
)

from apps.exercises.admin import DayStepsInlineBase, ExerciseInlineBase
from apps.libs.admin import round_field
from apps.measurements.models import Measurement

from ..models import Day, WeekPlan
from .day import DayAdmin
from .intake import IntakeInlineBase


# pylint: disable=too-few-public-methods
class IntakeInline(IntakeInlineBase, NestedTabularInline):
    """Intake inline class."""


class ExerciseInline(ExerciseInlineBase, NestedTabularInline):
    """Exercise inline class."""


class DayStepsInline(DayStepsInlineBase, NestedTabularInline):
    """DaySteps inline class."""


class DayInline(NestedTabularInline):
    """Day inline class."""

    model = Day
    extra = 0
    max_num = 0
    show_change_link = True

    inlines = [
        IntakeInline,
        ExerciseInline,
        DayStepsInline,
    ]

    fields = copy.deepcopy(DayAdmin.fields)
    readonly_fields = copy.deepcopy(DayAdmin.readonly_fields)


@admin.register(WeekPlan)
class WeekPlanAdmin(NestedModelAdmin):
    """WeekPLan admin class."""

    autocomplete_fields = [
        "user",
    ]

    inlines = [
        DayInline,
    ]

    list_display = [
        "id",
        "user",
        "start_date",
        "completed",
        round_field("protein_g_kg"),
        round_field("fat_perc"),
        round_field("deficit"),
        round_field("twee"),
        round_field("calorie_goal"),
        round_field("energy"),
        round_field("calorie_intake_perc"),
        round_field("calorie_deficit"),
    ]

    fields = [
        "user",
        "measurement",
        "start_date",
        "protein_g_kg",
        "fat_perc",
        "deficit",
        "twee",
        "calorie_goal",
        "energy",
        "calorie_intake_perc",
        "calorie_deficit",
    ]

    readonly_fields = [
        "twee",
        "calorie_goal",
        "energy",
        "calorie_intake_perc",
        "calorie_deficit",
    ]

    def get_changeform_initial_data(self, request: HttpRequest) -> Dict:
        """Get initial data for the change form.

        Args:
            request (HttpRequest): request object.

        Returns:
            dict: initial data.
        """
        res: Dict[str, Any] = {}

        # User
        res["user"] = request.user

        # Measurement
        res["measurement"] = (
            Measurement.objects.filter(user=res["user"])
            .order_by("-created_at")
            .first()
        )

        # Start date
        last_week = WeekPlan.objects.filter(user=res["user"]).last()
        if not last_week:
            return res

        res["start_date"] = last_week.start_date + datetime.timedelta(days=7)

        # Protein
        res["protein_g_kg"] = last_week.protein_g_kg

        # Fat
        res["fat_perc"] = last_week.fat_perc

        # Deficit
        res["deficit"] = last_week.deficit

        return res
