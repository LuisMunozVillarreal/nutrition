"""Admin libraries."""

from typing import List, Type

from apps.foods.models import FoodProduct, Recipe


def get_remaining_fields(model: Type[FoodProduct | Recipe], fields: List[str]):
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
