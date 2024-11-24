"""Foods admin base module."""

from django.db.models.query import QuerySet


class TagsAdminMixin:
    """Tags admin mixin class."""

    def get_queryset(self, request) -> QuerySet:
        """Get queryset.

        Args:
            request (request): user request.

        Returns:
            QuerySet: queryset.
        """
        return super().get_queryset(request).prefetch_related("tags")

    def tag_list(self, obj) -> str:
        """Get tag list.

        Args:
            obj (FoodProduct): FoodProduct instance.

        Returns:
            str: tag list.
        """
        return ", ".join(o.name for o in obj.tags.all())
