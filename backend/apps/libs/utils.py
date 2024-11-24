"""Utility functions."""

from decimal import Decimal


def round_no_trailing_zeros(value: Decimal, decimals: int = 2) -> Decimal:
    """Round value without trailing zeros.

    Args:
        value (Decimal): value to round.
        decimals (int): number of decimals.

    Returns:
        Decimal: rounded value.
    """
    return Decimal(str(round(value * 10**decimals))) / 10**decimals
