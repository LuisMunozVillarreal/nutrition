"""measuremnts app admin config module."""

from decimal import Decimal

from django.contrib import admin

from apps.libs.admin import round_no_trailing_zeros

from .models import Measurement


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    """MeasurementAdmin class."""

    list_display = [
        "id",
        "user",
        "created_at",
        "body_fat_perc",
        "weight",
        "rounded_bmr",
    ]

    fields = [
        "user",
        "created_at",
        "body_fat_perc",
        "weight",
        "rounded_bmr",
    ]

    readonly_fields = [
        "created_at",
        "rounded_bmr",
    ]

    def rounded_bmr(self, obj) -> Decimal:
        """Get rounded BMR.

        Args:
            obj (Measurement): measurement object.

        Returns:
            Decimal: rounded BMR.
        """
        return round_no_trailing_zeros(obj.bmr, 2)
