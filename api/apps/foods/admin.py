"""foods app admin config module."""


from django.contrib import admin

from apps.libs.admin import get_remaining_fields

from .models import Food, FoodProduct, Recipe, RecipeIngredient


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    """FoodAdmin class."""

    search_fields = [
        "brand",
        "name",
    ]

    def get_model_perms(self, request):
        """Get model perms.

        Return empty perms dict thus hiding the model from admin index.

        Args:
            request (object): user request.

        Returns:
            Dict: model perms
        """
        return {}


@admin.register(FoodProduct)
class FoodProductAdmin(admin.ModelAdmin):
    """FoodProductAdmin class."""

    search_fields = [
        "brand",
        "name",
    ]

    list_display = [
        "id",
        "brand",
        "name",
        "serving_size",
        "serving_unit",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    _main_fields = [
        "brand",
        "name",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
        "serving_size",
        "serving_unit",
        "url",
        "barcode",
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
                "fields": get_remaining_fields(FoodProduct, _main_fields),
            },
        ),
    ]


class RecipeIngredientInline(admin.TabularInline):
    """RecipeIngredientInline class."""

    model = RecipeIngredient
    show_change_link = True

    autocomplete_fields = [
        "food",
    ]

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
        "serving_size",
        "num_ingredients",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    _main_fields = [
        "brand",
        "name",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
        "serving_size",
        "serving_unit",
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
