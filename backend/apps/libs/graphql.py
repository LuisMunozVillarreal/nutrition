"""Shared helpers for GraphQL request contexts."""

import math
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


def validated_decimal_field(
    value: Decimal,
    field_name: str,
    model_field: models.DecimalField,
) -> Decimal:
    """Require a decimal to be exactly representable by its model field.

    Args:
        value: Decimal value to validate.
        field_name: GraphQL field name used in the validation error.
        model_field: Destination Django decimal field.

    Returns:
        The exactly representable decimal value.

    Raises:
        ValueError: If the destination field cannot represent the value.
    """
    try:
        return model_field.clean(value, None)
    except ValidationError as exc:
        raise ValueError(f"{field_name} exceeds supported precision") from exc


def validated_positive_decimal(
    value: float,
    field_name: str,
    model_field: models.DecimalField | None = None,
) -> Decimal:
    """Return a finite positive decimal for a GraphQL numeric input.

    Args:
        value: Numeric input to validate.
        field_name: GraphQL field name used in the validation error.
        model_field: Optional destination field whose precision must support value.

    Returns:
        The validated value as a decimal.

    Raises:
        ValueError: If the value is invalid or cannot be represented exactly.
    """
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    decimal_value = Decimal(str(value))
    if model_field is not None:
        return validated_decimal_field(decimal_value, field_name, model_field)
    return decimal_value


def validated_non_negative_decimal(
    value: float,
    field_name: str,
    model_field: models.DecimalField | None = None,
) -> Decimal:
    """Return a finite non-negative decimal for a GraphQL numeric input.

    Args:
        value: Numeric input to validate.
        field_name: GraphQL field name used in the validation error.
        model_field: Optional destination field whose precision must support value.

    Returns:
        The validated value as a decimal.

    Raises:
        ValueError: If the value is invalid or cannot be represented exactly.
    """
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    decimal_value = Decimal(str(value))
    if model_field is not None:
        return validated_decimal_field(decimal_value, field_name, model_field)
    return decimal_value


def validated_percentage_decimal(
    value: float,
    field_name: str,
    model_field: models.DecimalField | None = None,
) -> Decimal:
    """Return a finite decimal strictly between zero and one hundred.

    Args:
        value: Percentage input to validate.
        field_name: GraphQL field name used in the validation error.
        model_field: Optional destination field whose precision must support value.

    Returns:
        The validated value as a decimal.

    Raises:
        ValueError: If the value is invalid or cannot be represented exactly.
    """
    if not math.isfinite(value) or not 0 < value < 100:
        raise ValueError(
            f"{field_name} must be greater than 0 and less than 100"
        )
    decimal_value = Decimal(str(value))
    if model_field is not None:
        return validated_decimal_field(decimal_value, field_name, model_field)
    return decimal_value


def get_request_user(context: Any) -> Any:
    """Return an authenticated user from a Django or wrapped request context.

    Args:
        context: A Django request or a Strawberry context containing one.

    Returns:
        The authenticated Django user, or None.
    """
    request = getattr(context, "request", context)
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return user
