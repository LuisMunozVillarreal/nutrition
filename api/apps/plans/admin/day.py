"""Day admin config module."""


import copy

from django.contrib import admin

from apps.exercises.models import DaySteps, Exercise

from ..models import Day, Intake
from .intake import IntakeAdmin


class IntakeInline(admin.TabularInline):
    """Intake inline class."""

    model = Intake
    show_change_link = True

    ordering = copy.deepcopy(IntakeAdmin.ordering)
    fields = copy.deepcopy(IntakeAdmin.fields)
    readonly_fields = copy.deepcopy(IntakeAdmin.readonly_fields)


class ExerciseInline(admin.TabularInline):
    """Exercise inline class."""

    model = Exercise
    show_change_link = True

    fields = [
        "type",
        "kcals",
        "duration",
        "distance",
    ]


class DayStepsInline(admin.TabularInline):
    """DaySteps inline class."""

    model = DaySteps
    show_change_link = True

    fields = [
        "steps",
        "kcals",
    ]

    readonly_fields = [
        "kcals",
    ]


@admin.register(Day)
class DayAdmin(admin.ModelAdmin):
    """Day admin class."""

    inlines = [
        IntakeInline,
        ExerciseInline,
        DayStepsInline,
    ]

    list_display = [
        "id",
        "plan",
        "day",
        "day_num",
        "deficit",
        "tracked",
        "num_foods",
        "tdee",
        "calorie_goal",
        "calorie_intake_perc",
        "protein_g_goal",
        "protein_g_intake_perc",
        "fat_g_goal",
        "fat_g_intake_perc",
        "carbs_g_goal",
        "carbs_g_intake_perc",
    ]

    fields = [
        "plan",
        "day",
        "day_num",
        "deficit",
        "tracked",
        "num_foods",
        "tdee",
        "calorie_goal",
        "calorie_intake_perc",
        "calorie_deficit",
        "calorie_surplus",
        "protein_g_goal",
        "protein_g",
        "protein_g_intake_perc",
        "fat_g_goal",
        "fat_g",
        "fat_g_intake_perc",
        "carbs_g_goal",
        "carbs_g",
        "carbs_g_intake_perc",
    ]

    readonly_fields = [
        "num_foods",
        "tdee",
        "calorie_goal",
        "calorie_intake_perc",
        "calorie_deficit",
        "calorie_surplus",
        "protein_g_goal",
        "protein_g",
        "protein_g_intake_perc",
        "fat_g_goal",
        "fat_g",
        "fat_g_intake_perc",
        "carbs_g_goal",
        "carbs_g",
        "carbs_g_intake_perc",
    ]
