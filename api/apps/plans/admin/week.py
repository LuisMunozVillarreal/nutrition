"""week admin config module."""


import copy

from django.contrib import admin
from nested_inline.admin import NestedModelAdmin, NestedTabularInline

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
        "protein_kg",
        "fat_perc",
        "deficit",
        "estimated_twee",
        "protein_g_goal_week",
        "estimated_tdee",
        "protein_g_goal_day",
        "remaining_days",
        "calorie_deficit",
        "calorie_intake_perc",
        "protein_intake_perc",
    ]

    fields = [
        "user",
        "measurement",
        "start_date",
        "protein_kg",
        "fat_perc",
        "deficit",
        "estimated_twee",
        "protein_g_goal_week",
        "estimated_tdee",
        "protein_g_goal_day",
        "remaining_days",
        "calorie_deficit",
        "calorie_intake_perc",
        "protein_intake_perc",
    ]

    readonly_fields = [
        "estimated_twee",
        "protein_g_goal_week",
        "estimated_tdee",
        "protein_g_goal_day",
        "remaining_days",
        "calorie_deficit",
        "calorie_intake_perc",
        "protein_intake_perc",
    ]
