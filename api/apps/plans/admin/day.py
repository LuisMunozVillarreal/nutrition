"""Day admin config module."""


from django.contrib import admin

from apps.exercises.admin import DayStepsInlineBase, ExerciseInlineBase

from ..models import Day
from .intake import IntakeInlineBase


class IntakeInline(  # type: ignore[misc]
    IntakeInlineBase,
    admin.TabularInline,
):
    """Intake inline class."""


class ExerciseInline(  # type: ignore[misc]
    ExerciseInlineBase,
    admin.TabularInline,
):
    """Exercise inline class."""


class DayStepsInline(  # type: ignore[misc]
    DayStepsInlineBase,
    admin.TabularInline,
):
    """DaySteps inline class."""


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
        "day",
        "day_num",
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
