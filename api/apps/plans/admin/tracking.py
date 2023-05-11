"""tracking admin config module."""


from django.contrib import admin

from apps.exercises.models import DaySteps, Exercise

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


class ExerciseInline(admin.TabularInline):
    """Exercise inline class."""

    model = Exercise
    show_change_link = True

    fields = [
        "type",
        "kcals",
        "duration",
        "distance",
    ]


class DayStepsInline(admin.TabularInline):
    """DaySteps inline class."""

    model = DaySteps
    show_change_link = True

    fields = [
        "steps",
        "kcals",
    ]

    readonly_fields = [
        "kcals",
    ]


@admin.register(DayTracking)
class DayTrackingAdmin(admin.ModelAdmin):
    """DayTracking admin class."""

    inlines = [
        DayFoodInline,
        ExerciseInline,
        DayStepsInline,
    ]

    list_display = [
        "id",
        "plan",
        "day",
        "num_foods",
        "tdee",
        "estimated_calorie_goal",
        "calorie_intake",
        "protein_intake_g",
    ]

    fields = [
        "plan",
        "day",
        "num_foods",
        "tdee",
        "estimated_calorie_goal",
        "calorie_intake_perc",
        "calorie_deficit",
        "protein_intake_g",
    ]

    readonly_fields = [
        "num_foods",
        "tdee",
        "estimated_calorie_goal",
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
        "day",
        "time",
        "food",
        "meal",
        "serving_size",
        "serving_unit",
        "calories",
        "protein_g",
    ]

    fields = [
        "day",
        "time",
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
