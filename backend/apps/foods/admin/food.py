"""foods app admin config module."""

from django.contrib import admin
from django.http.request import HttpRequest

from ..models import Food


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    """FoodAdmin class."""

    search_fields = [
        "brand",
        "name",
        "tags__name",
    ]

    def get_model_perms(self, request: HttpRequest) -> dict:
        """Get model perms.

        Return empty perms dict thus hiding the model from admin index.

        Args:
            request (object): user request.

        Returns:
            Dict: model perms
        """
        return {}
