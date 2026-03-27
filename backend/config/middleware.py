"""JWT Authentication Middleware for Django."""

from typing import Any, Callable, cast

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

User = get_user_model()


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
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=["HS256"],
                )
                user_id = payload.get("sub")
                if user_id:
                    try:
                        request.user = cast(Any, User.objects.get(pk=user_id))
                    except User.DoesNotExist:
                        request.user = AnonymousUser()
            except jwt.ExpiredSignatureError:
                request.user = AnonymousUser()
            except jwt.InvalidTokenError:
                request.user = AnonymousUser()

        return self.get_response(request)
