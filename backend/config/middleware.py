"""JWT Authentication Middleware for Django."""

from typing import Any, Callable, cast

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

User = get_user_model()


def authenticated_request_user(request: Any) -> Any:
    """Return the request principal, prioritising any Authorization header.

    Args:
        request: The request-like object containing authentication state.

    Returns:
        The authenticated user, or ``None`` when authentication fails.
    """
    auth_header = getattr(request, "META", {}).get("HTTP_AUTHORIZATION", "")
    if not auth_header:
        user = getattr(request, "user", None)
        return user if user is not None and user.is_authenticated else None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        payload = jwt.decode(
            parts[1],
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
        user_id = payload.get("sub")
        if not user_id:
            return None
        return User.objects.get(pk=user_id, is_active=True)
    except (
        jwt.InvalidTokenError,
        TypeError,
        ValueError,
        User.DoesNotExist,
    ):
        return None


class JWTAuthenticationMiddleware:
    """Decode JWT Bearer tokens and set request.user.

    Reads the Authorization header, decodes the JWT using
    settings.SECRET_KEY, and attaches the corresponding user to
    the request so that Strawberry resolvers can access it via
    ``info.context.user``.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        """Initialise middleware.

        Args:
            get_response (callable): the next middleware / view.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request.

        Args:
            request (HttpRequest): the incoming request.

        Returns:
            HttpResponse: the response from the next middleware.
        """
        if request.META.get("HTTP_AUTHORIZATION", ""):
            request.user = cast(
                Any, authenticated_request_user(request) or AnonymousUser()
            )

        return self.get_response(request)
