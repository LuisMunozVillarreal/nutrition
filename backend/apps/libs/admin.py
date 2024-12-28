"""Admin libraries."""

from typing import Any, Callable, Dict, List, Type

from django.http import HttpRequest

from apps.foods.models.product import FoodProduct
from apps.foods.models.recipe import Recipe

from .utils import round_no_trailing_zeros


def get_remaining_fields(
    model: Type[FoodProduct | Recipe], fields: List[str]
) -> List[str]:
    """Get remaining fields of the model.

    Args:
        model (Model): Django model.
        fields (List[str]): list of fields.

    Returns:
        List[str]: list of extra fields.
    """
    field_names = []

    for field in model._meta.fields:
        if (
            field.editable
            and field.name != "id"
            and "ptr" not in field.name
            and field.name not in fields
        ):
            field_names.append(field.name)

    return field_names


def round_field(field_name: str, decimals: int = 2) -> Callable:
    """Round field for admin view.

    Args:
        field_name (str): field name.
        decimals (int): number of decimals.

    Returns:
        Callable: rounded field.
    """

    def _round_field(obj: Any) -> str:
        field = getattr(obj, field_name)
        if field is None:
            return "-"

        return str(round_no_trailing_zeros(field, decimals))

    _round_field.short_description = field_name  # type: ignore[attr-defined]

    return _round_field


class LoggedUserAsDefaultMixin:
    """Logged User as default mixin."""

    # pylint: disable=too-few-public-methods

    def get_changeform_initial_data(self, request: HttpRequest) -> Dict:
        """Get initial data for the change form.

        Args:
            request (HttpRequest): request object.

        Returns:
            dict: initial data.
        """
        return {"user": request.user}
