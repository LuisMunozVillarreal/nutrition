"""admin config for servings module."""


from django.contrib import admin

from ..models import Serving


@admin.register(Serving)
class ServingAdmin(admin.ModelAdmin):
    """ServingAdmin class."""

    search_fields = [
        "food__brand",
        "food__name",
        "size",
        "unit",
    ]

    def has_add_permission(self, request, obj=None):
        """Get whether it has add permission.

        Overriden to prevent Servings being added from the admin panel.

        Args:
            request (request): user request.
            obj (Serving): object related to the request.

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
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    fields = [
        "size",
        "unit",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]
