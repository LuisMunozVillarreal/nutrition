"""admin config for food products module."""


from django.contrib import admin

from apps.libs.admin import get_remaining_fields

from ..models import FoodProduct
from .serving import ServingInline


@admin.register(FoodProduct)
class FoodProductAdmin(admin.ModelAdmin):
    """FoodProductAdmin class."""

    inlines = [
        ServingInline,
    ]

    search_fields = [
        "brand",
        "name",
    ]

    list_display = [
        "id",
        "brand",
        "name",
        "weight",
        "weight_unit",
        "num_servings",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    _main_fields = [
        "brand",
        "name",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
        "url",
        "barcode",
        "nutritional_info_size",
        "nutritional_info_unit",
        "weight",
        "weight_unit",
        "num_servings",
    ]

    fieldsets = [
        (
            "General",
            {
                "fields": [
                    "brand",
                    "name",
                    "url",
                    "barcode",
                    "weight",
                    "weight_unit",
                    "num_servings",
                ],
            },
        ),
        (
            "Nutrition",
            {
                "fields": [
                    "nutritional_info_size",
                    "nutritional_info_unit",
                    "energy",
                    "fat_g",
                    "carbs_g",
                    "protein_g",
                ],
            },
        ),
        (
            "Extra nutrients",
            {
                "classes": ["collapse"],
                "fields": get_remaining_fields(FoodProduct, _main_fields),
            },
        ),
    ]
