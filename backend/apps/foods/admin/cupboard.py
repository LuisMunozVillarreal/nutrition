"""admin config for cupboard items module."""

from django.contrib import admin

from apps.foods.models.cupboard import CupboardItem


@admin.register(CupboardItem)
class CupboardItemAdmin(admin.ModelAdmin):
    """CupboardItem Admin class."""

    autocomplete_fields = [
        "food",
    ]

    list_display = [
        "id",
        "food",
        "food__num_servings",
        "consumed_servings",
        "consumed_perc",
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
