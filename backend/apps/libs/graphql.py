"""Shared helpers for GraphQL request contexts."""

from typing import Any


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
