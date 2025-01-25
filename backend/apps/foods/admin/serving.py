"""admin config for servings module."""

from django.contrib import admin
from django.http import HttpRequest

from apps.libs.admin import round_field

from ..models import Serving


@admin.register(Serving)
class ServingAdmin(admin.ModelAdmin):
    """ServingAdmin class."""

    search_fields = [
        "food__brand",
        "food__name",
        "food__tags__name",
        "size",
        "unit",
    ]

    list_display = [
        "id",
        "food__brand",
        "food__name",
        "size",
        "unit",
        round_field("energy_kcal"),
        round_field("protein_g"),
        round_field("fat_g"),
        round_field("carbs_g"),
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Get whether it has add permission.

        Overriden to prevent Servings being added from the admin panel.

        Args:
            request (request): user request.

        Returns:
            bool: whether it has add permission.
        """
        # pylint: disable=unused-argument

        return False


class ServingInline(admin.TabularInline):
    """ServingInline admin class."""

    model = Serving
    show_change_link = True
    extra = 0

    list_fields = [
        "size",
        "unit",
        "energy_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    fields = [
        "size",
        "unit",
        "energy_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]
