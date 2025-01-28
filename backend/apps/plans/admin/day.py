"""Day admin config module."""

from django.contrib import admin
from django.http import HttpRequest

from apps.exercises.admin import DayStepsInlineBase, ExerciseInlineBase
from apps.libs.admin import round_field

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
        "weekday",
        "day_num",
        "completed",
        "breakfast_flag",
        "lunch_flag",
        "snack_flag",
        "dinner_flag",
        "exercises_flag",
        "steps_flag",
        "deficit",
        round_field("energy_kcal_goal"),
        round_field("energy_kcal"),
        round_field("energy_kcal_intake_perc"),
        "energy_kcal_goal_diff",
        "energy_kcal_goal_accumulated_diff",
        round_field("fat_g_goal"),
        round_field("fat_g"),
        round_field("fat_g_intake_perc"),
        round_field("carbs_g_goal"),
        round_field("carbs_g"),
        round_field("carbs_g_intake_perc"),
        round_field("protein_g_goal"),
        round_field("protein_g"),
        round_field("protein_g_intake_perc"),
    ]

    fields = [
        "plan",
        "day",
        "weekday",
        "day_num",
        "completed",
        "breakfast_flag",
        "breakfast_exc",
        "lunch_flag",
        "lunch_exc",
        "snack_flag",
        "snack_exc",
        "dinner_flag",
        "dinner_exc",
        "exercises_flag",
        "exercises_exc",
        "steps_flag",
        "steps_exc",
        "deficit",
        "tracked",
        "num_foods",
        "tdee",
        "energy_kcal_goal",
        "energy_kcal",
        "energy_kcal_intake_perc",
        "energy_kcal_goal_diff",
        "energy_kcal_goal_accumulated_diff",
        "fat_g_goal",
        "fat_g",
        "fat_g_intake_perc",
        "carbs_g_goal",
        "carbs_g",
        "carbs_g_intake_perc",
        "protein_g_goal",
        "protein_g",
        "protein_g_intake_perc",
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
        "tdee",
        "energy_kcal",
        "energy_kcal_goal",
        "energy_kcal_intake_perc",
        "energy_kcal_goal_diff",
        "energy_kcal_goal_accumulated_diff",
        "fat_g_goal",
        "fat_g",
        "fat_g_intake_perc",
        "carbs_g_goal",
        "carbs_g",
        "carbs_g_intake_perc",
        "protein_g_goal",
        "protein_g",
        "protein_g_intake_perc",
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
