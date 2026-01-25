"""JWT Authentication Middleware."""

from typing import Any, Callable, cast

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse

User = get_user_model()


class JWTAuthenticationMiddleware:
    # pylint: disable=too-few-public-methods
    """Middleware to authenticate users via JWT."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process request to add user if token is valid."""
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(
                    token, settings.SECRET_KEY, algorithms=["HS256"]
                )
                user_id = payload.get("sub")
                if user_id:
                    # Sync call is fine in WSGI
                    user = User.objects.get(pk=user_id)
                    request.user = cast(Any, user)
            except (
                jwt.ExpiredSignatureError,
                jwt.DecodeError,
                User.DoesNotExist,
            ):
                # Token is invalid or user does not exist
                pass

        return self.get_response(request)
