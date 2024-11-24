"""week admin config module."""

import copy

from django.contrib import admin
from nested_inline.admin import (  # type: ignore[import]
    NestedModelAdmin,
    NestedTabularInline,
)

from apps.exercises.admin import DayStepsInlineBase, ExerciseInlineBase
from apps.libs.admin import round_field

from ..models import Day, WeekPlan
from .day import DayAdmin
from .intake import IntakeInlineBase


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
