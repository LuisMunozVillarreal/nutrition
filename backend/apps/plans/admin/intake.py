"""Intake admin config module."""


import copy

from django.contrib import admin

from ..models import Intake


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    """Intake admin class."""

    # pylint: disable=duplicate-code

    ordering = [
        "meal_order",
    ]

    autocomplete_fields = [
        "food",
    ]

    list_display = [
        "id",
        "day",
        "food",
        "meal",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    fields = [
        "day",
        "food",
        "meal",
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
