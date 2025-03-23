"""Day admin config module."""

from django import forms
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from apps.exercises.admin import DayStepsInlineBase, ExerciseInlineBase
from apps.libs.admin import progress_bar_field, round_field

from ..models import Day
from .intake import IntakeInlineBase


class IntakeInline(  # type: ignore[misc]
    IntakeInlineBase,
    admin.TabularInline,
):
    """Intake inline class."""

    formfield_overrides = {
        models.TextField: {"widget": forms.Textarea(attrs={"rows": 1})},
        models.DecimalField: {
            "widget": forms.NumberInput(
                attrs={"step": 1, "style": "width: 40px"}
            )
        },
    }


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
        "weekday",
        "day_num",
        "completed",
        progress_bar_field("energy_kcal_intake_perc", "Energy"),
        progress_bar_field("fat_g_intake_perc", "Fat"),
        progress_bar_field("carbs_g_intake_perc", "Carbs"),
        progress_bar_field("protein_g_intake_perc", "Protein"),
        round_field("energy_kcal_goal", 2, "Energy Goal"),
        round_field("energy_kcal", 2, "Intake"),
        round_field("energy_kcal_intake_perc", 2, "%"),
        round_field("energy_kcal_goal_diff", 2, "Diff"),
        round_field("energy_kcal_goal_accumulated_diff", 2, "Acc Diff"),
        round_field("fat_g_goal", 2, "Fat Goal"),
        round_field("fat_g", 2, "Intake"),
        round_field("fat_g_intake_perc", 2, "%"),
        round_field("carbs_g_goal", 2, "Carbs Goal"),
        round_field("carbs_g", 2, "Intake"),
        round_field("carbs_g_intake_perc", 2, "%"),
        round_field("protein_g_goal", 2, "Protein Goal"),
        round_field("protein_g", 2, "Intake"),
        round_field("protein_g_intake_perc", 2, "%"),
        "breakfast_flag",
        "lunch_flag",
        "snack_flag",
        "dinner_flag",
        "exercises_flag",
        "steps_flag",
        "deficit",
    ]

    fieldsets = [
        (
            "General",
            {
                "classes": ["collapse"],
                "fields": [
                    (
                        "plan",
                        "day",
                        "weekday",
                        "day_num",
                        "deficit",
                    ),
                ],
            },
        ),
        (
            None,
            {
                "fields": [
                    "completed",
                    (
                        "energy_kcal_intake_progress_bar",
                        "fat_g_intake_progress_bar",
                        "carbs_g_intake_progress_bar",
                        "protein_g_intake_progress_bar",
                    ),
                ],
            },
        ),
        (
            "Stats",
            {
                "classes": ["collapse"],
                "fields": [
                    (
                        "round_tdee",
                        "energy_kcal_goal_diff",
                        "energy_kcal_goal_accumulated_diff",
                        "num_foods",
                    ),
                    (
                        "energy_kcal",
                        "energy_kcal_goal",
                        "energy_kcal_intake_perc",
                    ),
                    ("fat_g_goal", "fat_g", "fat_g_intake_perc"),
                    ("carbs_g_goal", "carbs_g", "carbs_g_intake_perc"),
                    ("protein_g_goal", "protein_g", "protein_g_intake_perc"),
                ],
            },
        ),
        (
            "Flags",
            {
                "classes": ["collapse"],
                "fields": [
                    ("breakfast_flag", "breakfast_exc"),
                    ("lunch_flag", "lunch_exc"),
                    ("snack_flag", "snack_exc"),
                    ("dinner_flag", "dinner_exc"),
                    ("exercises_flag", "exercises_exc"),
                    ("steps_flag", "steps_exc"),
                ],
            },
        ),
        (
            None,
            {
                "fields": ["tracked"],
            },
        ),
    ]

    readonly_fields = [
        "day",
        "weekday",
        "day_num",
        "completed",
        "breakfast_flag",
        "lunch_flag",
        "snack_flag",
        "dinner_flag",
        "exercises_flag",
        "steps_flag",
        "num_foods",
        "round_tdee",
        "energy_kcal_intake_progress_bar",
        "energy_kcal",
        "energy_kcal_goal",
        "energy_kcal_intake_perc",
        "energy_kcal_goal_diff",
        "energy_kcal_goal_accumulated_diff",
        "fat_g_goal",
        "fat_g",
        "fat_g_intake_perc",
        "fat_g_intake_progress_bar",
        "carbs_g_goal",
        "carbs_g",
        "carbs_g_intake_perc",
        "carbs_g_intake_progress_bar",
        "protein_g_goal",
        "protein_g",
        "protein_g_intake_perc",
        "protein_g_intake_progress_bar",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Get whether it has add permission.

        Overriden to prevent Days being added from the admin panel.

        Args:
            request (request): user request.

        Returns:
            bool: whether it has add permission.
        """
        # pylint: disable=unused-argument

        return False
