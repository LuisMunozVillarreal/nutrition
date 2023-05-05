"""measuremnts app admin config module."""


from django.contrib import admin

from .models import Measurement


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    """MeasurementAdmin class."""

    list_display = [
        "id",
        "user",
        "created_at",
        "fat_perc",
        "weight",
        "bmr",
    ]

    fields = [
        "user",
        "created_at",
        "fat_perc",
        "weight",
        "bmr",
    ]

    readonly_fields = [
        "created_at",
        "bmr",
    ]
