"""Intake admin config module."""


from django.contrib import admin

from ..models import Intake


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    """Intake admin class."""

    ordering = [
        "meal_order",
    ]

    list_display = [
        "id",
        "day",
        "food",
        "meal",
        "serving_size",
        "serving_unit",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    fields = [
        "day",
        "food",
        "meal",
        "serving_size",
        "serving_unit",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    readonly_fields = [
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]
