"""GraphQL coverage for Garmin auth and isolation boundaries."""

from __future__ import annotations

import jwt
import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model

import config.schema as schema_module
from apps.garmin.services import GarminTokenPair

User = get_user_model()


def _configure_garmin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GARMIN_ENABLED", True)
    monkeypatch.setattr(settings, "GARMIN_CLIENT_ID", "garmin-client-id")
    monkeypatch.setattr(settings, "GARMIN_CLIENT_SECRET", "garmin-secret")
    monkeypatch.setattr(
        settings, "GARMIN_AUTHORIZATION_URL", "https://garmin.example.com/auth"
    )
    monkeypatch.setattr(
        settings, "GARMIN_TOKEN_URL", "https://garmin.example.com/token"
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_ACTIVITIES_URL",
        "https://garmin.example.com/activities",
    )
    monkeypatch.setattr(
        settings, "GARMIN_CALLBACK_URL", "https://app.example.com/callback"
    )
    monkeypatch.setattr(settings, "GARMIN_SCOPES", "read write")
    monkeypatch.setattr(settings, "GARMIN_REQUEST_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_PAGES", 3)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITIES_LIMIT", 100)
    monkeypatch.setattr(settings, "GARMIN_STATE_TTL_SECONDS", 300)
    monkeypatch.setattr(settings, "GARMIN_STATE_MAX_IN_FLIGHT", 3)
    monkeypatch.setattr(settings, "GARMIN_TOKEN_MAX_TTL_SECONDS", 3600)
    monkeypatch.setattr(
        settings,
        "GARMIN_ACTIVITY_ENDPOINT_MAX_RESPONSE_BYTES",
        1024 * 1024,
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_TOKEN_ENDPOINT_MAX_RESPONSE_BYTES",
        512 * 1024,
    )
    monkeypatch.setattr(
        settings, "GARMIN_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


def _create_user(email: str):
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


def _request_context(user, *, bearer: bool = False):
    request = type("Request", (), {"user": user, "META": {}})()
    if bearer:
        request.META["HTTP_AUTHORIZATION"] = "Bearer " + jwt.encode(
            {"sub": str(user.id)},
            settings.SECRET_KEY,
            algorithm="HS256",
        )
    return type("Context", (), {"request": request})()


def test_begin_garmin_authorization_requires_authentication():
    """Unauthorized callers cannot start Garmin authorization flow."""
    result = schema_module.schema.execute_sync("""
            mutation {
                beginGarminAuthorization {
                    authorizationUrl
                    state
                    expiresAt
                }
            }
        """)

    assert result.errors is not None
    assert "Authentication required" in result.errors[0].message


def test_complete_garmin_authorization_replays_state_once(monkeypatch):
    """State can be consumed one time and then cannot be replayed."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-replay@example.com")
    context = _request_context(user, bearer=True)

    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        lambda _: GarminTokenPair(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            provider_account_id="provider-user",
            scope="read",
        ),
    )

    begin_result = schema_module.schema.execute_sync(
        """
            mutation {
                beginGarminAuthorization {
                    state
                }
            }
        """,
        context_value=context,
    )
    assert begin_result.errors is None
    state = begin_result.data["beginGarminAuthorization"]["state"]

    complete = schema_module.schema.execute_sync(
        """
            mutation($code: String!, $state: String!) {
                completeGarminAuthorization(code: $code, state: $state) {
                    connected
                }
            }
        """,
        variable_values={"code": "auth-code", "state": state},
        context_value=context,
    )
    assert complete.errors is None
    assert complete.data["completeGarminAuthorization"]["connected"] is True

    replay = schema_module.schema.execute_sync(
        """
            mutation($code: String!, $state: String!) {
                completeGarminAuthorization(code: $code, state: $state) {
                    connected
                }
            }
        """,
        variable_values={"code": "auth-code", "state": state},
        context_value=context,
    )
    assert replay.errors is not None


def test_complete_garmin_authorization_consumes_state_even_when_exchange_fails(
    monkeypatch,
):
    """State remains consumed when the token exchange raises."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-replay-fail@example.com")
    context = _request_context(user, bearer=True)

    call_count = {"tokens": 0}

    def _explode(code: str) -> GarminTokenPair:
        call_count["tokens"] += 1
        raise ValueError("token exchange failed")

    monkeypatch.setattr(schema_module, "exchange_code_for_tokens", _explode)

    begin_result = schema_module.schema.execute_sync(
        """
            mutation {
                beginGarminAuthorization {
                    state
                }
            }
        """,
        context_value=context,
    )
    assert begin_result.errors is None
    state = begin_result.data["beginGarminAuthorization"]["state"]

    first = schema_module.schema.execute_sync(
        """
            mutation($code: String!, $state: String!) {
                completeGarminAuthorization(code: $code, state: $state) {
                    connected
                }
            }
        """,
        variable_values={"code": "auth-code", "state": state},
        context_value=context,
    )
    assert first.errors is not None

    second = schema_module.schema.execute_sync(
        """
            mutation($code: String!, $state: String!) {
                completeGarminAuthorization(code: $code, state: $state) {
                    connected
                }
            }
        """,
        variable_values={"code": "auth-code", "state": state},
        context_value=context,
    )
    assert second.errors is not None
    assert call_count["tokens"] == 1


def test_garmin_manual_sync_mutation_is_not_exposed():
    """Garmin sync is not executed inline from GraphQL."""
    user = _create_user("garmin-no-sync@example.com")

    result = schema_module.schema.execute_sync(
        """
            mutation {
                syncGarmin {
                    imported invalid
                }
            }
        """,
        context_value=_request_context(user, bearer=True),
    )

    assert result.errors is not None
    assert any("syncGarmin" in error.message for error in result.errors)


def test_garmin_mutations_require_bearer_authentication(monkeypatch):
    """Session-authenticated users need bearer tokens."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-bearer@example.com")
    context = _request_context(user, bearer=False)

    result = schema_module.schema.execute_sync(
        """
            mutation {
                beginGarminAuthorization {
                    state
                }
            }
        """,
        context_value=context,
    )

    assert result.errors is not None
    assert "Authentication required" in result.errors[0].message
