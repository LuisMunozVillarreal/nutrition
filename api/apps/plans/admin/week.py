"""week admin config module."""


import copy

from django.contrib import admin
from nested_inline.admin import (  # typing: ignore
    NestedModelAdmin,
    NestedTabularInline,
)

from ..models import Day, Intake, WeekPlan
from .day import DayAdmin
from .intake import IntakeAdmin


class IntakeInline(NestedTabularInline):
    """Intake inline class."""

    model = Intake
    extra = 0
    show_change_link = True

    ordering = copy.deepcopy(IntakeAdmin.ordering)
    fields = copy.deepcopy(IntakeAdmin.fields)
    readonly_fields = copy.deepcopy(IntakeAdmin.readonly_fields)


class DayInline(NestedTabularInline):
    """Day inline class."""

    model = Day
    extra = 0
    show_change_link = True

    inlines = [
        IntakeInline,
    ]

    fields = copy.deepcopy(DayAdmin.fields)
    readonly_fields = copy.deepcopy(DayAdmin.readonly_fields)


@admin.register(WeekPlan)
class WeekPlanAdmin(NestedModelAdmin):
    """WeekPLan admin class."""

    inlines = [
        DayInline,
    ]

    list_display = [
        "id",
        "user",
        "start_date",
        "protein_g_kg",
        "fat_perc",
        "deficit",
        "twee",
        "calorie_goal",
        "calories",
        "calorie_intake_perc",
        "calorie_deficit",
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
        "calories",
        "calorie_intake_perc",
        "calorie_deficit",
    ]

    readonly_fields = [
        "twee",
        "calorie_goal",
        "calories",
        "calorie_intake_perc",
        "calorie_deficit",
    ]
