from django.contrib import admin

from apps.foods.models.cupboard import CupboardItem


@admin.register(CupboardItem)
class CupboardItemAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "food",
        "started",
        "finished",
        "purchased_at",
        "consumed_perc",
    ]

    readonly_fields = [
        "started",
        "finished",
        "consumed_perc",
    ]
