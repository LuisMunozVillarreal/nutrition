"""admin config for recipe module."""

from decimal import Decimal

from django.contrib import admin

from apps.libs.admin import round_field
from apps.libs.utils import round_no_trailing_zeros

from ..models import Recipe, RecipeIngredient
from .base import TagsAdminMixin


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
        "energy_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    readonly_fields = [
        "energy_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]


@admin.register(Recipe)
class RecipeAdmin(TagsAdminMixin, admin.ModelAdmin):
    """RecipeAdmin class."""

    inlines = [
        RecipeIngredientInline,
    ]

    list_display = [
        "id",
        "name",
        "tag_list",
        round_field("num_servings"),
        "num_ingredients",
        "energy_p_s",
        "protein_p_s",
        "fat_p_s",
        "carbs_p_s",
        round_field("energy_kcal"),
        round_field("protein_g"),
        round_field("fat_g"),
        round_field("carbs_g"),
    ]

    fieldsets = [
        (
            None,
            {
                "fields": [
                    "brand",
                    "name",
                    "tags",
                    "energy_kcal",
                    "protein_g",
                    "fat_g",
                    "carbs_g",
                    "size",
                    "size_unit",
                    "num_servings",
                    "url",
                    "description",
                    "nutrients_from_ingredients",
                ],
            },
        ),
        (
            "Extra nutrients",
            {
                "classes": ["collapse"],
                "fields": [
                    "saturated_fat_g",
                    "polyunsaturated_fat_g",
                    "monosaturated_fat_g",
                    "trans_fat_g",
                    "fibre_carbs_g",
                    "salt_g",
                    "sugar_carbs_g",
                    "sodium_mg",
                    "potassium_mg",
                    "vitamin_a_perc",
                    "vitamin_c_perc",
                    "calcium_perc",
                    "iron_perc",
                    "abv_perc",
                    "nutritional_info_size",
                    "nutritional_info_unit",
                ],
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
        return round_no_trailing_zeros(obj.energy_kcal / obj.num_servings, 1)

    @admin.display(description="Protein p/s")
    def protein_p_s(self, obj: Recipe) -> Decimal:
        """Get protein per serving.

        Args:
            obj (Recipe): Recipe instance.

        Returns:
            Decimal: Protein per serving
        """
        return round_no_trailing_zeros(obj.protein_g / obj.num_servings, 1)

    @admin.display(description="Fat p/s")
    def fat_p_s(self, obj: Recipe) -> Decimal:
        """Get fat per serving.

        Args:
            obj (Recipe): Recipe instance.

        Returns:
            Decimal: Fat per serving
        """
        return round_no_trailing_zeros(obj.fat_g / obj.num_servings, 1)

    @admin.display(description="Carbs p/s")
    def carbs_p_s(self, obj: Recipe) -> Decimal:
        """Get carbs per serving.

        Args:
            obj (Recipe): Recipe instance.

        Returns:
            Decimal: Carbs per serving
        """
        return round_no_trailing_zeros(obj.carbs_g / obj.num_servings, 1)
