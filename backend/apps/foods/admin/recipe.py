"""admin config for recipe module."""

from decimal import Decimal

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
        "energy_p_s",
        "protein_p_s",
        "fat_p_s",
        "carbs_p_s",
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

    @admin.display(description="Energy p/s")
    def energy_p_s(self, obj: Recipe) -> Decimal:
        """Get energy per serving.

        Args:
           obj (Recipe): Recipe instance.

        Returns:
            Decimal: Energy per serving.
        """
        return round(obj.energy / obj.num_servings, 1)

    @admin.display(description="Protein p/s")
    def protein_p_s(self, obj: Recipe) -> Decimal:
        """Get protein per serving.

        Args:
            obj (Recipe): Recipe instance.

        Returns:
            Decimal: Protein per serving
        """
        return round(obj.protein_g / obj.num_servings, 1)

    @admin.display(description="Fat p/s")
    def fat_p_s(self, obj: Recipe) -> Decimal:
        """Get fat per serving.

        Args:
            obj (Recipe): Recipe instance.

        Returns:
            Decimal: Fat per serving
        """
        return round(obj.fat_g / obj.num_servings, 1)

    @admin.display(description="Carbs p/s")
    def carbs_p_s(self, obj: Recipe) -> Decimal:
        """Get carbs per serving.

        Args:
            obj (Recipe): Recipe instance.

        Returns:
            Decimal: Carbs per serving
        """
        return round(obj.carbs_g / obj.num_servings, 1)
