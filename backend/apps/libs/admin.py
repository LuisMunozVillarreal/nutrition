"""Admin libraries."""

from typing import Any, Callable, Dict, List, Type

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html

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


def round_field(
    field_name: str, decimals: int = 2, description: str = ""
) -> Callable:
    """Round field for admin view.

    Args:
        field_name (str): field name.
        decimals (int): number of decimals.
        description (str): description of field

    Returns:
        Callable: rounded field.
    """

    @admin.display(description=description or field_name, ordering=field_name)
    def _round_field(obj: Any) -> str:
        field = getattr(obj, field_name)
        if field is None:
            return "-"

        return str(round_no_trailing_zeros(field, decimals))

    return _round_field


def progress_bar_field(field_name: str, description: str) -> Callable:
    """Progress bar field for admin view.

    Args:
        field_name (str): field name.
        description (str): description of field.

    Returns:
        Callable: progress bar field.
    """

    @admin.display(description=description, ordering=field_name)
    def _progress_bar_field(obj: Any) -> str:
        return progress_bar(obj, field_name)

    return _progress_bar_field


def progress_bar(obj: Any, field_name: str) -> str:
    """Get progress bar.

    Args:
        obj (Any): object.
        field_name (str): field name.

    Returns:
        str: progress bar.
    """
    perc = getattr(obj, field_name)
    if perc is None:
        return "-"

    if perc <= 100:
        return format_html(
            """
            <progress style="accent-color: green" value="{0}" max="100">
            </progress>
            """,
            perc,
        )

    progress_bars = """
        <progress style="accent-color: green" value="100" max="100">
        </progress>
        """
    perc -= 100
    while True:
        if perc > 100:
            progress_bars += """
                <progress style="accent-color: red" value="100" max="100">
                </progress>
                """
            perc -= 100
        else:
            break

    progress_bars += """
        <progress style="accent-color: red" value="{0}" max="100">
        </progress>
        """
    return format_html(progress_bars, perc)


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
