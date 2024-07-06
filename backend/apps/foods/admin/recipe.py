"""admin config for recipe module."""

from django.contrib import admin

from apps.libs.admin import get_remaining_fields

from ..models import Recipe, RecipeIngredient


class RecipeIngredientInline(admin.TabularInline):
    """RecipeIngredientInline class."""

    model = RecipeIngredient
    show_change_link = True
    extra = 0

    autocomplete_fields = [
        "food",
    ]

    fields = [
        "food",
        # "serving",
        "num_servings",
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


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """RecipeAdmin class."""

    inlines = [
        RecipeIngredientInline,
    ]

    list_display = [
        "id",
        "name",
        "num_servings",
        "num_ingredients",
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
        "weight",
        "weight_unit",
        "num_servings",
        "url",
        "description",
        "nutrients_from_ingredients",
    ]

    fieldsets = [
        (
            None,
            {
                "fields": _main_fields,
            },
        ),
        (
            "Extra nutrients",
            {
                "classes": ["collapse"],
                "fields": get_remaining_fields(Recipe, _main_fields),
            },
        ),
    ]
