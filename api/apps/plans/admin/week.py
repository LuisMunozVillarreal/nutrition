"""week admin config module."""


import copy

from django.contrib import admin
from nested_inline.admin import NestedModelAdmin, NestedTabularInline

from ..models import DayFood, DayTracking, WeekPlan
from .tracking import DayFoodAdmin, DayTrackingAdmin


class DayFoodInline(NestedTabularInline):
    """DayFood inline class."""

    model = DayFood
    extra = 0
    show_change_link = True

    ordering = copy.deepcopy(DayFoodAdmin.ordering)
    fields = copy.deepcopy(DayFoodAdmin.fields)
    readonly_fields = copy.deepcopy(DayFoodAdmin.readonly_fields)


class DayTrackingInline(NestedTabularInline):
    """DayTracking inline class."""

    model = DayTracking
    extra = 0
    show_change_link = True

    inlines = [
        DayFoodInline,
    ]

    fields = copy.deepcopy(DayTrackingAdmin.fields)

    readonly_fields = copy.deepcopy(DayTrackingAdmin.readonly_fields)


@admin.register(WeekPlan)
class WeekPlanAdmin(NestedModelAdmin):
    """WeekPLan admin class."""

    inlines = [
        DayTrackingInline,
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
