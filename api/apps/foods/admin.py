"""foods app admin config module."""


from django.contrib import admin

from .models import Food, Recipe, RecipeIngredient


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    """FoodAdmin class."""

    list_display = [
        "id",
        "brand",
        "name",
        "serving_size",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]


class RecipeIngredientInline(admin.TabularInline):
    """RecipeIngredientInline class."""

    model = RecipeIngredient
    show_change_link = True

    fields = [
        "food",
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


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """RecipeAdmin class."""

    inlines = [
        RecipeIngredientInline,
    ]

    list_display = [
        "id",
        "name",
        "number_of_servings",
        "num_ingredients",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]
