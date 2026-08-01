"""GraphQL coverage for Garmin auth and isolation boundaries."""

from __future__ import annotations

import jwt
import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model

import config.schema as schema_module
from apps.garmin.models import GarminConnection
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
    monkeypatch.setattr(
        settings,
        "GARMIN_PROVIDER_ORIGINS",
        ["https://garmin.example.com"],
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_CALLBACK_ALLOWED_ORIGINS",
        ["https://app.example.com"],
    )
    monkeypatch.setattr(settings, "GARMIN_SCOPES", "read write")
    monkeypatch.setattr(settings, "GARMIN_REQUEST_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_PAGES", 3)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITIES_LIMIT", 100)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_TOTAL_ITEMS", 10000)
    monkeypatch.setattr(
        settings,
        "GARMIN_ACTIVITY_ENDPOINT_MAX_TOTAL_BYTES",
        5 * 1024 * 1024,
    )
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


def _create_connection_with_tokens(user):
    connection = GarminConnection.objects.create(user=user)
    token_pair = GarminTokenPair(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_in=3600,
        scope="read write",
        provider_account_id="provider-user",
    )
    connection.set_tokens(token_pair, expires_in=token_pair.expires_in)
    connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_account_id",
            "provider_scopes",
            "status",
            "connection_generation",
            "updated_at",
        ]
    )
    return connection


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
    assert "Garmin connection state changed during authorization" in str(
        first.errors[0].message
    )

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


def test_complete_garmin_auth_rejects_connection_change(
    monkeypatch,
):
    """Disconnecting during token exchange should reject persistence."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-authorization-race@example.com")
    context = _request_context(user, bearer=True)

    _create_connection_with_tokens(user)

    call_count = {"tokens": 0}

    def _exchange(code: str) -> GarminTokenPair:
        call_count["tokens"] += 1
        connection = GarminConnection.objects.get(user=user)
        connection.clear_tokens()
        connection.save(
            update_fields=[
                "access_token_encrypted",
                "refresh_token_encrypted",
                "provider_scopes",
                "provider_account_id",
                "provider",
                "access_token_expires_at",
                "status",
                "connection_generation",
                "last_synced_at",
                "last_sync_summary",
                "updated_at",
            ]
        )
        return GarminTokenPair(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            scope="read",
            provider_account_id="provider-user",
        )

    monkeypatch.setattr(schema_module, "exchange_code_for_tokens", _exchange)

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

    connection = GarminConnection.objects.get(user=user)
    assert connection.status == GarminConnection.Status.DISCONNECTED


def test_complete_garmin_authorization_uses_router_alias_with_user_instance(
    monkeypatch,
):
    """Oauth completion must use the user-sharded write router for updates."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-complete-router@example.com")
    context = _request_context(user, bearer=True)

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

    db_calls: list[tuple[object, object | None]] = []

    def _db_for_write(model, instance=None):
        db_calls.append((model, instance))
        return "default"

    monkeypatch.setattr(schema_module.router, "db_for_write", _db_for_write)
    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        lambda *_: GarminTokenPair(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            scope="read",
            provider_account_id="provider-user",
        ),
    )

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
    assert all(model.__name__ == "GarminConnection" for model, _ in db_calls)
    assert all(
        instance is not None
        and instance.__class__.__name__ == "User"
        and instance.pk == user.pk
        for _, instance in db_calls
    )


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


def test_disconnect_garmin_clears_tokens_without_decryption(monkeypatch):
    """Disconnect must clear locally even when token decryption breaks."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-disconnect-key-rotation@example.com")
    _create_connection_with_tokens(user)
    monkeypatch.setattr(
        settings,
        "GARMIN_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )

    result = schema_module.schema.execute_sync(
        """
            mutation {
                disconnectGarmin
            }
        """,
        context_value=_request_context(user, bearer=True),
    )

    assert result.errors is None
    assert result.data["disconnectGarmin"] is True

    connection = GarminConnection.objects.get(user=user)
    assert connection.access_token_encrypted == ""
    assert connection.refresh_token_encrypted == ""
    assert connection.status == GarminConnection.Status.DISCONNECTED


def test_disconnect_garmin_still_clears_locally_if_revoke_fails(monkeypatch):
    """Remote revocation failures should not prevent local credential wipe."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-disconnect-revoke-failure@example.com")
    _create_connection_with_tokens(user)

    def _revoke(_token: str) -> None:
        raise ValueError("revoke failed")

    monkeypatch.setattr(schema_module, "revoke_refresh_token", _revoke)

    result = schema_module.schema.execute_sync(
        """
            mutation {
                disconnectGarmin
            }
        """,
        context_value=_request_context(user, bearer=True),
    )

    assert result.errors is None
    assert result.data["disconnectGarmin"] is True

    connection = GarminConnection.objects.get(user=user)
    assert connection.access_token_encrypted == ""
    assert connection.refresh_token_encrypted == ""
