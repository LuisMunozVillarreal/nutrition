"""tracking admin config module."""


from django.contrib import admin

from ..models import DayFood, DayTracking


class DayFoodInline(admin.TabularInline):
    """DayFood inline class."""

    model = DayFood
    show_change_link = True
    ordering = [
        "meal_order",
    ]

    fields = [
        "food",
        "meal",
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


@admin.register(DayTracking)
class DayTrackingAdmin(admin.ModelAdmin):
    """DayTracking admin class."""

    inlines = [
        DayFoodInline,
    ]

    list_display = [
        "id",
        "plan",
        "day",
        "num_foods",
        "tdee",
        "calorie_goal",
        "calorie_intake",
        "protein_intake_g",
    ]

    fields = [
        "plan",
        "day",
        "num_foods",
        "tdee",
        "calorie_goal",
        "calorie_intake_perc",
        "calorie_deficit",
        "protein_intake_g",
    ]

    readonly_fields = [
        "num_foods",
        "tdee",
        "calorie_goal",
        "calorie_intake_perc",
        "calorie_deficit",
        "protein_intake_g",
    ]


@admin.register(DayFood)
class DayFoodAdmin(admin.ModelAdmin):
    """DayFood admin class."""

    ordering = [
        "meal_order",
    ]

    list_display = [
        "id",
        "food",
        "meal",
        "serving_size",
        "serving_unit",
        "calories",
        "protein_g",
    ]

    fields = [
        "day",
        "food",
        "meal",
        "serving_size",
        "serving_unit",
        "calories",
        "protein_g",
    ]

    readonly_fields = [
        "calories",
        "protein_g",
    ]
