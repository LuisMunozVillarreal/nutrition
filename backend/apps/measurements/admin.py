"""measurements app admin config module."""

from django.contrib import admin

from apps.libs.admin import LoggedUserAsDefaultMixin, round_field

from .models import Measurement


@admin.register(Measurement)
class MeasurementAdmin(LoggedUserAsDefaultMixin, admin.ModelAdmin):
    """MeasurementAdmin class."""

    list_display = [
        "id",
        "user",
        "created_at",
        round_field("body_fat_perc"),
        round_field("weight"),
        round_field("bmr"),
    ]

    fields = [
        "user",
        "created_at",
        "body_fat_perc",
        "weight",
        "bmr",
    ]

    readonly_fields = [
        "created_at",
        "bmr",
    ]
