"""admin config for cupboard items module."""

from django.contrib import admin

from apps.foods.models.cupboard import CupboardItem
from apps.libs.admin import round_field
from apps.libs.utils import round_no_trailing_zeros


@admin.register(CupboardItem)
class CupboardItemAdmin(admin.ModelAdmin):
    """CupboardItem Admin class."""

    autocomplete_fields = [
        "food",
    ]

    list_display = [
        "id",
        "food",
        "round_food_num_servings",
        round_field("consumed_servings"),
        round_field("consumed_perc"),
        "started",
        "finished",
        "purchased_at",
    ]

    readonly_fields = [
        "started",
        "finished",
        "consumed_servings",
        "consumed_perc",
    ]

    def round_food_num_servings(self, obj: CupboardItem) -> str:
        """Get rounded food num servings.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            str: rounded food num servings.
        """
        return str(round_no_trailing_zeros(obj.food.num_servings))
