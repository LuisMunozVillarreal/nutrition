"""week admin config module."""

import copy
import datetime
from decimal import Decimal
from typing import Any, Dict

from django.contrib import admin
from django.http import HttpRequest

# pylint: disable=no-name-in-module
from nested_admin import (  # type: ignore[import]
    NestedModelAdmin,
    NestedTabularInline,
)

from apps.exercises.admin import DayStepsInlineBase, ExerciseInlineBase
from apps.libs.utils import round_no_trailing_zeros
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
        "protein_g_kg",
        "fat_perc",
        "deficit",
        "rounded_twee",
        "rounded_calorie_goal",
        "rounded_energy",
        "rounded_calorie_intake_perc",
        "rounded_calorie_deficit",
    ]

    fields = [
        "user",
        "measurement",
        "start_date",
        "protein_g_kg",
        "fat_perc",
        "deficit",
        "rounded_twee",
        "rounded_calorie_goal",
        "rounded_energy",
        "rounded_calorie_intake_perc",
        "rounded_calorie_deficit",
    ]

    readonly_fields = [
        "rounded_twee",
        "rounded_calorie_goal",
        "rounded_energy",
        "rounded_calorie_intake_perc",
        "rounded_calorie_deficit",
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

    def rounded_twee(self, obj: WeekPlan) -> Decimal:
        """Get rounded twee.

        Args:
            obj (WeekPlan): instance of the object.

        Returns:
            str: rounded twee.
        """
        return round_no_trailing_zeros(obj.twee)

    def rounded_calorie_goal(self, obj: WeekPlan) -> Decimal:
        """Get rounded calorie goal.

        Args:
            obj (WeekPlan): instance of the object.

        Returns:
            str: rounded calorie goal.
        """
        return round_no_trailing_zeros(obj.calorie_goal)

    def rounded_energy(self, obj: WeekPlan) -> Decimal:
        """Get rounded energy.

        Args:
            obj (WeekPlan): instance of the object.

        Returns:
            str: rounded energy.
        """
        return round_no_trailing_zeros(obj.energy)

    def rounded_calorie_intake_perc(self, obj: WeekPlan) -> Decimal:
        """Get rounded calorie intake percentage.

        Args:
            obj (WeekPlan): instance of the object.

        Returns:
            str: rounded calorie intake percentage.
        """
        return round_no_trailing_zeros(obj.calorie_intake_perc)

    def rounded_calorie_deficit(self, obj: WeekPlan) -> Decimal:
        """Get rounded calorie deficit.

        Args:
            obj (WeekPlan): instance of the object.

        Returns:
            str: rounded calorie deficit.
        """
        return round_no_trailing_zeros(obj.calorie_deficit)
