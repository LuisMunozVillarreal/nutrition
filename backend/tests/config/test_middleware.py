"""Tests for JWT authentication middleware."""

import secrets
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


def run_middleware(request):
    """Return the principal observed after JWT middleware processing."""
    observed_user = None

    def get_response(processed_request):
        nonlocal observed_user
        observed_user = processed_request.user
        return HttpResponse()

    JWTAuthenticationMiddleware(get_response)(request)
    return observed_user


@pytest.mark.django_db
def test_lowercase_bearer_token_overrides_existing_session_user():
    """Authorization schemes are case-insensitive and bearer wins over cookies."""
    bearer_user = User.objects.create_user(
        email="lowercase-bearer@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    session_user = User.objects.create_user(
        email="existing-session@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    token = jwt.encode(
        {
            "sub": str(bearer_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    request = RequestFactory().get(
        "/graphql/", HTTP_AUTHORIZATION=f"bearer {token}"
    )
    request.user = session_user

    assert run_middleware(request) == bearer_user


@pytest.mark.django_db
@pytest.mark.parametrize(
    "authorization",
    ["Basic credentials", "Bearer", "bearer invalid-token", "   "],
)
def test_authorization_header_failures_clear_existing_session_user(
    authorization,
):
    """Any unusable Authorization header fails closed instead of using cookies."""
    session_user = User.objects.create_user(
        email=f"session-{secrets.token_hex(4)}@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    request = RequestFactory().get(
        "/graphql/", HTTP_AUTHORIZATION=authorization
    )
    request.user = session_user

    assert isinstance(run_middleware(request), AnonymousUser)


@pytest.mark.django_db
@pytest.mark.parametrize("claims", [{}, {"sub": ""}])
def test_bearer_without_subject_clears_existing_session_user(claims):
    """A signed bearer without a subject is not an authenticated principal."""
    session_user = User.objects.create_user(
        email=f"session-{secrets.token_hex(4)}@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    token = jwt.encode(
        {
            **claims,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    request = RequestFactory().get(
        "/graphql/", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    request.user = session_user

    assert isinstance(run_middleware(request), AnonymousUser)


@pytest.mark.django_db
def test_expired_bearer_clears_existing_session_user():
    """An expired backend token cannot fall back to a live Django session."""
    session_user = User.objects.create_user(
        email="expired-session@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    token = jwt.encode(
        {
            "sub": str(session_user.id),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    request = RequestFactory().get(
        "/graphql/", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    request.user = session_user

    assert isinstance(run_middleware(request), AnonymousUser)


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
    session_user = User.objects.create_user(
        email="active-session@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
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
    request.user = session_user

    assert isinstance(run_middleware(request), AnonymousUser)
