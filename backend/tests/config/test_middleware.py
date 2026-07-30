"""Tests for JWT authentication middleware."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory

from config.middleware import JWTAuthenticationMiddleware

User = get_user_model()


@pytest.mark.django_db
def test_bearer_token_rejects_inactive_user():
    """An inactive user cannot authenticate through middleware."""
    user = User.objects.create_user(
        email="inactive-middleware@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
        is_active=False,
    )
    token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    request = RequestFactory().get(
        "/graphql/", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    request.user = AnonymousUser()
    observed_user = None

    def get_response(processed_request):
        nonlocal observed_user
        observed_user = processed_request.user
        return HttpResponse()

    JWTAuthenticationMiddleware(get_response)(request)

    assert isinstance(observed_user, AnonymousUser)
