"""admin config for cupboard items module."""

from django.contrib import admin

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
        "purchased_at",
    ]

    readonly_fields = [
        "started",
        "finished",
        "consumed_servings",
        "consumed_perc",
    ]

    @admin.display(description="Num Servings")
    def round_food_num_servings(self, obj: CupboardItem) -> str:
        """Get rounded food num servings.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            str: rounded food num servings.
        """
        return str(round_no_trailing_zeros(obj.food.num_servings))

    @admin.display(description="Remaining")
    def round_remaining_servings(self, obj: CupboardItem) -> str:
        """Get remaining servings with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            str: remaining servings.
        """
        return str(round_no_trailing_zeros(obj.remaining_servings))

    @admin.display(description="Consumed")
    def round_consumed_servings(self, obj: CupboardItem) -> str:
        """Get consumed servings with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            str: consumed servings.
        """
        return str(round_no_trailing_zeros(obj.consumed_servings))

    @admin.display(description="%")
    def round_consumed_perc(self, obj: CupboardItem) -> str:
        """Get consumed percentage with displayed description.

        Args:
            obj (CupboardItem): cupboard item object.

        Returns:
            str: consumed percentage.
        """
        return str(round_no_trailing_zeros(obj.consumed_perc))
