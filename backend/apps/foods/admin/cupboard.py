"""admin config for cupboard items module."""

from decimal import Decimal

from django.contrib import admin
from django.db.models import F

from apps.foods.models.cupboard import CupboardItem
from apps.libs.utils import round_no_trailing_zeros


@admin.register(CupboardItem)
class CupboardItemAdmin(admin.ModelAdmin):
    """CupboardItem Admin class."""

    autocomplete_fields = [
        "food",
    ]

    list_filter = [
        "finished",
    ]

    list_display = [
        "id",
        "food",
        "round_food_num_servings",
        "round_remaining_servings",
        "round_consumed_servings",
        "round_consumed_perc",
        "started",
        "finished",
        "round_energy_kcal_per_serving",
        "round_fat_g_per_serving",
        "round_carbs_g_per_serving",
        "round_protein_g_per_serving",
        "purchased_at",
    ]

    readonly_fields = [
        "started",
        "finished",
        "consumed_servings",
        "consumed_perc",
    ]

    @admin.display(description="Num Servings", ordering="food__num_servings")
    def round_food_num_servings(self, obj: CupboardItem) -> Decimal:
        """Get rounded food num servings.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: rounded food num servings.
        """
        return round_no_trailing_zeros(obj.food.num_servings)

    @admin.display(
        description="Remaining",
        ordering=F("food__num_servings")
        - F("food__num_servings") * F("consumed_perc") / 100,
    )
    def round_remaining_servings(self, obj: CupboardItem) -> Decimal:
        """Get remaining servings with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: remaining servings.
        """
        return round_no_trailing_zeros(obj.remaining_servings)

    @admin.display(
        description="Consumed",
        ordering=F("food__num_servings") * F("consumed_perc") / 100,
    )
    def round_consumed_servings(self, obj: CupboardItem) -> Decimal:
        """Get consumed servings with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: consumed servings.
        """
        return round_no_trailing_zeros(obj.consumed_servings)

    @admin.display(description="%", ordering="consumed_perc")
    def round_consumed_perc(self, obj: CupboardItem) -> Decimal:
        """Get consumed percentage with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: consumed percentage.
        """
        return round_no_trailing_zeros(obj.consumed_perc)

    @admin.display(
        description="Energy/s",
        ordering=F("food__energy") / F("food__num_servings"),
    )
    def round_energy_kcal_per_serving(self, obj: CupboardItem) -> Decimal:
        """Get energy kcal per serving with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: energy kcal per serving.
        """
        return round_no_trailing_zeros(obj.energy_kcal_per_serving)

    @admin.display(
        description="Fat/s",
        ordering=F("food__fat_g") / F("food__num_servings"),
    )
    def round_fat_g_per_serving(self, obj: CupboardItem) -> Decimal:
        """Get fat grams per serving with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: fat grams per serving.
        """
        return round_no_trailing_zeros(obj.fat_g_per_serving)

    @admin.display(
        description="Carbs/s",
        ordering=F("food__carbs_g") / F("food__num_servings"),
    )
    def round_carbs_g_per_serving(self, obj: CupboardItem) -> Decimal:
        """Get carbs grams per serving with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: carbs grams per serving.
        """
        return round_no_trailing_zeros(obj.carbs_g_per_serving)

    @admin.display(
        description="Protein/s",
        ordering=F("food__protein_g") / F("food__num_servings"),
    )
    def round_protein_g_per_serving(self, obj: CupboardItem) -> Decimal:
        """Get protein grams per serving with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            Decimal: protein grams per serving.
        """
        return round_no_trailing_zeros(obj.protein_g_per_serving)
