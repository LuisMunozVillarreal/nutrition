"""Intake admin config module."""

import copy
import datetime
from typing import Any, Dict

from django.contrib import admin
from django.http import HttpRequest

from apps.libs.admin import round_field

from ..models import Day, Intake, IntakePicture


class IntakePictureInline(admin.TabularInline):
    """Intake picture inline class."""

    model = IntakePicture
    extra = 0
    show_change_link = True


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    """Intake admin class."""

    # pylint: disable=duplicate-code

    inlines = [
        IntakePictureInline,
    ]

    ordering = [
        "-day__plan",
        "-day__day",
        "meal_order",
    ]

    autocomplete_fields = [
        "food",
    ]

    list_display = [
        "id",
        "day",
        "food",
        round_field("num_servings"),
        "meal",
        "processed",
        round_field("energy"),
        round_field("protein_g"),
        round_field("fat_g"),
        round_field("carbs_g"),
    ]

    fields = [
        "day",
        "food",
        "num_servings",
        "meal",
        "notes",
        "processed",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    readonly_fields = [
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    def get_changeform_initial_data(self, request: HttpRequest) -> Dict:
        """Get initial data for the change form.

        Args:
            request (HttpRequest): request object.

        Returns:
            dict: initial data.
        """
        res: Dict[str, Any] = {}

        # Day
        day = Day.objects.filter(day=datetime.date.today()).first()
        if day:
            res["day"] = day.id

        # Meal
        time = datetime.datetime.now().time()
        if datetime.time(8) < time < datetime.time(12):
            res["meal"] = Intake.MEAL_BREAKFAST
        elif time < datetime.time(15):
            res["meal"] = Intake.MEAL_LUNCH
        elif time < datetime.time(20):
            res["meal"] = Intake.MEAL_SNACK
        else:
            res["meal"] = Intake.MEAL_DINNER

        return res


class IntakeInlineBase:
    """Intake inline class."""

    # pylint: disable=too-few-public-methods

    model = Intake
    extra = 0
    show_change_link = True

    autocomplete_fields = [
        "food",
    ]

    ordering = copy.deepcopy(IntakeAdmin.ordering)
    fields = copy.deepcopy(IntakeAdmin.fields)
    readonly_fields = copy.deepcopy(IntakeAdmin.readonly_fields)
