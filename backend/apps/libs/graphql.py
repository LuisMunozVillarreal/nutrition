"""Shared helpers for GraphQL request contexts."""

import math
from decimal import Decimal
from typing import Any


def validated_positive_decimal(value: float, field_name: str) -> Decimal:
    """Return a finite positive decimal for a GraphQL numeric input.

    Args:
        value: Numeric input to validate.
        field_name: GraphQL field name used in the validation error.

    Returns:
        The validated value as a decimal.

    Raises:
        ValueError: If the value is non-finite or not greater than zero.
    """
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return Decimal(str(value))


def validated_non_negative_decimal(value: float, field_name: str) -> Decimal:
    """Return a finite non-negative decimal for a GraphQL numeric input.

    Args:
        value: Numeric input to validate.
        field_name: GraphQL field name used in the validation error.

    Returns:
        The validated value as a decimal.

    Raises:
        ValueError: If the value is non-finite or less than zero.
    """
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return Decimal(str(value))


def validated_percentage_decimal(value: float, field_name: str) -> Decimal:
    """Return a finite decimal strictly between zero and one hundred.

    Args:
        value: Percentage input to validate.
        field_name: GraphQL field name used in the validation error.

    Returns:
        The validated value as a decimal.

    Raises:
        ValueError: If the value is non-finite or outside the open range.
    """
    if not math.isfinite(value) or not 0 < value < 100:
        raise ValueError(
            f"{field_name} must be greater than 0 and less than 100"
        )
    return Decimal(str(value))


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
