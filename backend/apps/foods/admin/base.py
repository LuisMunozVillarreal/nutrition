"""Foods admin base module."""

from typing import Any

from django.db.models.query import QuerySet
from django.http.request import HttpRequest


class TagsAdminMixin:
    """Tags admin mixin class."""

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Get queryset.

        Args:
            request (request): user request.

        Returns:
            QuerySet: queryset.
        """
        return (
            super()  # type: ignore[misc]
            .get_queryset(request)
            .prefetch_related("tags")
        )

    def tag_list(self, obj: Any) -> str:
        """Get tag list.

        Args:
            obj (FoodProduct): FoodProduct instance.

        Returns:
            str: tag list.
        """
        return ", ".join(o.name for o in obj.tags.all())
