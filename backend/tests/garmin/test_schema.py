"""GraphQL coverage for Garmin auth and isolation boundaries."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import jwt
import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

import config.schema as schema_module
from apps.garmin.models import (
    GARMIN_PROVIDER,
    GarminActivity,
    GarminConnection,
    GarminOAuthState,
)
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


def _begin_state(context) -> str:
    """Start authorization and return its one-time state."""
    result = schema_module.schema.execute_sync(
        """
            mutation {
                beginGarminAuthorization { state }
            }
        """,
        context_value=context,
    )
    assert result.errors is None
    return result.data["beginGarminAuthorization"]["state"]


def _complete_authorization(context, *, code: str, state: str):
    """Execute the Garmin completion mutation for a test callback."""
    return schema_module.schema.execute_sync(
        """
            mutation($code: String!, $state: String!) {
                completeGarminAuthorization(code: $code, state: $state) {
                    connected
                }
            }
        """,
        variable_values={"code": code, "state": state},
        context_value=context,
    )


def _cancel_authorization(context, *, state: str):
    """Execute the state-only Garmin cancellation mutation."""
    return schema_module.schema.execute_sync(
        """
            mutation($state: String!) {
                cancelGarminAuthorization(state: $state)
            }
        """,
        variable_values={"state": state},
        context_value=context,
    )


def _token_pair(account: str) -> GarminTokenPair:
    """Return deterministic provider-free callback credentials."""
    return GarminTokenPair(
        access_token=f"access-{account}",
        refresh_token=f"refresh-{account}",
        expires_in=3600,
        provider_account_id=account,
        scope="read",
    )


def _create_historical_activity(
    connection: GarminConnection,
    *,
    account: str,
    activity_id: str = "history-1",
) -> GarminActivity:
    """Create durable provider provenance without requiring a plan fixture."""
    return GarminActivity.objects.create(
        connection=connection,
        provider_activity_id=activity_id,
        provider_activity_type="cycle",
        provider_account_id=account,
        started_at=timezone.now(),
        kcals=100,
        duration_seconds=600,
        distance=Decimal("5.00"),
        pending_reconciliation=True,
        pending_reconciliation_reason="day_not_found",
    )


def _disconnect(context):
    """Execute the credential-erasing disconnect mutation."""
    return schema_module.schema.execute_sync(
        "mutation { disconnectGarmin }",
        context_value=context,
    )


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


def test_cancel_garmin_authorization_consumes_state_without_token_exchange(
    monkeypatch,
):
    """Provider cancellation consumes its slot and rejects state replay."""
    _configure_garmin(monkeypatch)
    monkeypatch.setattr(settings, "GARMIN_STATE_MAX_IN_FLIGHT", 1)
    user = _create_user("garmin-cancel@example.com")
    context = _request_context(user, bearer=True)
    state = _begin_state(context)

    def _unexpected_exchange(_code: str) -> GarminTokenPair:
        raise AssertionError("cancellation must not exchange a provider code")

    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        _unexpected_exchange,
    )
    blocked = schema_module.schema.execute_sync(
        "mutation { beginGarminAuthorization { state } }",
        context_value=context,
    )
    assert blocked.errors is not None

    cancelled = _cancel_authorization(context, state=state)

    assert cancelled.errors is None
    assert cancelled.data == {"cancelGarminAuthorization": True}
    consumed = GarminOAuthState.objects.get(
        user=user,
        provider=GARMIN_PROVIDER,
        state_hash=GarminOAuthState.hash_state(state),
    )
    assert consumed.consumed_at is not None
    replay = _cancel_authorization(context, state=state)
    assert replay.errors is not None
    assert replay.errors[0].message == "OAuth state is invalid or expired"
    replacement = _begin_state(context)
    assert replacement != state


@pytest.mark.parametrize("state", ["", "unknown-state"])
def test_cancel_garmin_authorization_rejects_invalid_state_with_redacted_error(
    monkeypatch,
    state,
):
    """Malformed and missing cancellation state fail with one safe message."""
    _configure_garmin(monkeypatch)
    user = _create_user(
        f"garmin-cancel-invalid-{state or 'empty'}@example.com"
    )

    result = _cancel_authorization(
        _request_context(user, bearer=True),
        state=state,
    )

    assert result.errors is not None
    assert result.errors[0].message == "OAuth state is invalid or expired"
    assert result.data is None


def test_cancel_garmin_authorization_rejects_expired_state_with_redacted_error(
    monkeypatch,
):
    """Expired cancellation state does not reveal why matching failed."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-cancel-expired@example.com")
    state = "expired-provider-error-state"
    GarminOAuthState.create_for_user(
        user=user,
        raw_state=state,
        provider=GARMIN_PROVIDER,
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    result = _cancel_authorization(
        _request_context(user, bearer=True),
        state=state,
    )

    assert result.errors is not None
    assert result.errors[0].message == "OAuth state is invalid or expired"
    oauth_state = GarminOAuthState.objects.get(user=user)
    assert oauth_state.consumed_at is None


def test_cancel_garmin_authorization_is_bearer_authenticated_and_owner_bound(
    monkeypatch,
):
    """Session auth and another owner cannot consume a callback state."""
    _configure_garmin(monkeypatch)
    owner = _create_user("garmin-cancel-owner@example.com")
    other = _create_user("garmin-cancel-other@example.com")
    state = _begin_state(_request_context(owner, bearer=True))

    session_only = _cancel_authorization(
        _request_context(owner, bearer=False),
        state=state,
    )
    wrong_owner = _cancel_authorization(
        _request_context(other, bearer=True),
        state=state,
    )

    assert session_only.errors is not None
    assert session_only.errors[0].message == "Authentication required"
    assert wrong_owner.errors is not None
    assert wrong_owner.errors[0].message == "OAuth state is invalid or expired"
    oauth_state = GarminOAuthState.objects.get(user=owner)
    assert oauth_state.consumed_at is None
    assert (
        _cancel_authorization(
            _request_context(owner, bearer=True),
            state=state,
        ).errors
        is None
    )


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
    connection = GarminConnection.objects.get(user=user)
    assert connection.status == GarminConnection.Status.ACTIVE
    assert connection.can_sync is True

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
    assert not GarminConnection.objects.filter(user=user).exists()

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


@pytest.mark.parametrize(
    "existing_status",
    [GarminConnection.Status.ACTIVE, GarminConnection.Status.DISCONNECTED],
)
def test_failed_reconnect_preserves_existing_connection(
    monkeypatch, existing_status
):
    """A failed exchange cannot delete or mutate an existing connection row."""
    _configure_garmin(monkeypatch)
    user = _create_user(f"garmin-reconnect-{existing_status}@example.com")
    context = _request_context(user, bearer=True)
    if existing_status == GarminConnection.Status.ACTIVE:
        connection = _create_connection_with_tokens(user)
    else:
        connection = GarminConnection.objects.create(
            user=user,
            status=GarminConnection.Status.DISCONNECTED,
        )
    initial_generation = connection.connection_generation
    snapshot = (
        connection.pk,
        connection.status,
        connection.provider,
        connection.provider_account_id,
        connection.provider_scopes,
        connection.access_token_encrypted,
        connection.refresh_token_encrypted,
        connection.access_token_expires_at,
        connection.last_synced_at,
        connection.last_sync_summary,
    )

    def _exchange_failure(_code: str) -> GarminTokenPair:
        raise ValueError("exchange failed")

    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        _exchange_failure,
    )

    begin_result = schema_module.schema.execute_sync(
        """
            mutation {
                beginGarminAuthorization { state }
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

    assert complete.errors is not None
    preserved = GarminConnection.objects.get(user=user)
    assert preserved.connection_generation == initial_generation + 1
    assert preserved.authorization_placeholder is False
    assert (
        preserved.pk,
        preserved.status,
        preserved.provider,
        preserved.provider_account_id,
        preserved.provider_scopes,
        preserved.access_token_encrypted,
        preserved.refresh_token_encrypted,
        preserved.access_token_expires_at,
        preserved.last_synced_at,
        preserved.last_sync_summary,
    ) == snapshot


def test_later_callback_owns_placeholder_when_first_exchange_fails(
    monkeypatch,
):
    """A failed callback cannot delete a placeholder superseded by callback B."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-callback-owner-failure@example.com")
    context = _request_context(user, bearer=True)
    state_a = _begin_state(context)
    state_b = _begin_state(context)
    nested_result = {}

    def _exchange(code: str) -> GarminTokenPair:
        if code == "code-a":
            nested_result["b"] = _complete_authorization(
                context,
                code="code-b",
                state=state_b,
            )
            raise ValueError("exchange failed")
        connection = GarminConnection.objects.get(user=user)
        assert connection.connection_generation == 3
        return _token_pair("account-b")

    monkeypatch.setattr(schema_module, "exchange_code_for_tokens", _exchange)

    result_a = _complete_authorization(context, code="code-a", state=state_a)

    assert result_a.errors is not None
    assert nested_result["b"].errors is None
    connection = GarminConnection.objects.get(user=user)
    assert connection.provider_account_id == "account-b"
    assert connection.is_connected is True


def test_superseded_successful_callback_fails_with_redacted_error(
    monkeypatch,
):
    """Callback A cannot persist success after callback B claims ownership."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-callback-owner-success@example.com")
    context = _request_context(user, bearer=True)
    state_a = _begin_state(context)
    state_b = _begin_state(context)
    nested_result = {}

    def _exchange(code: str) -> GarminTokenPair:
        if code == "code-a":
            nested_result["b"] = _complete_authorization(
                context,
                code="code-b",
                state=state_b,
            )
            return _token_pair("account-a")
        return _token_pair("account-b")

    monkeypatch.setattr(schema_module, "exchange_code_for_tokens", _exchange)

    result_a = _complete_authorization(context, code="code-a", state=state_a)

    assert nested_result["b"].errors is None
    assert result_a.errors is not None
    assert result_a.errors[0].message == (
        "Garmin connection state changed during authorization"
    )
    connection = GarminConnection.objects.get(user=user)
    assert connection.provider_account_id == "account-b"


def test_successful_callback_handles_concurrent_connection_removal(
    monkeypatch,
):
    """A removed callback row produces a deterministic redacted error."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-callback-removal@example.com")
    context = _request_context(user, bearer=True)
    state = _begin_state(context)

    def _exchange(_code: str) -> GarminTokenPair:
        GarminConnection.objects.filter(user=user).delete()
        return _token_pair("removed-account")

    monkeypatch.setattr(schema_module, "exchange_code_for_tokens", _exchange)

    result = _complete_authorization(context, code="code", state=state)

    assert result.errors is not None
    assert result.errors[0].message == (
        "Garmin connection state changed during authorization"
    )
    assert not GarminConnection.objects.filter(user=user).exists()


def test_latest_failed_callback_cleans_inherited_placeholder(monkeypatch):
    """Two failed initial callbacks do not leave an owned placeholder row."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-callback-double-failure@example.com")
    context = _request_context(user, bearer=True)
    state_a = _begin_state(context)
    state_b = _begin_state(context)
    nested_result = {}

    def _exchange(code: str) -> GarminTokenPair:
        if code == "code-a":
            nested_result["b"] = _complete_authorization(
                context,
                code="code-b",
                state=state_b,
            )
        raise ValueError("exchange failed")

    monkeypatch.setattr(schema_module, "exchange_code_for_tokens", _exchange)

    result_a = _complete_authorization(context, code="code-a", state=state_a)

    assert nested_result["b"].errors is not None
    assert result_a.errors is not None
    assert not GarminConnection.objects.filter(user=user).exists()


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


def test_disconnected_account_switch_with_history_is_rejected_without_side_effects(
    monkeypatch,
):
    """Historical account A provenance blocks reconnecting as account B."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-history-switch@example.com")
    other_user = _create_user("garmin-history-switch-other@example.com")
    context = _request_context(user, bearer=True)
    connection = _create_connection_with_tokens(user)
    activity = _create_historical_activity(
        connection,
        account="provider-user",
    )
    other_connection = _create_connection_with_tokens(other_user)
    other_snapshot = (
        other_connection.provider_account_id,
        other_connection.access_token_encrypted,
        other_connection.refresh_token_encrypted,
        other_connection.connection_generation,
    )
    activity_snapshot = tuple(
        GarminActivity.objects.filter(pk=activity.pk).values_list(
            "provider_account_id",
            "provider_activity_id",
            "day_id",
            "exercise_id",
            "kcals",
            "duration_seconds",
            "distance",
        )[0]
    )

    disconnected = _disconnect(context)
    assert disconnected.errors is None
    state = _begin_state(context)
    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        lambda _: _token_pair("provider-account-b"),
    )

    result = _complete_authorization(context, code="code-b", state=state)

    assert result.errors is not None
    assert result.errors[0].message == (
        "Garmin provider account cannot change while historical activities exist"
    )
    connection.refresh_from_db()
    assert connection.status == GarminConnection.Status.DISCONNECTED
    assert connection.provider_account_id == "provider-user"
    assert connection.access_token_encrypted == ""
    assert connection.refresh_token_encrypted == ""
    assert (
        tuple(
            GarminActivity.objects.filter(pk=activity.pk).values_list(
                "provider_account_id",
                "provider_activity_id",
                "day_id",
                "exercise_id",
                "kcals",
                "duration_seconds",
                "distance",
            )[0]
        )
        == activity_snapshot
    )
    other_connection.refresh_from_db()
    assert (
        other_connection.provider_account_id,
        other_connection.access_token_encrypted,
        other_connection.refresh_token_encrypted,
        other_connection.connection_generation,
    ) == other_snapshot


def test_same_account_reconnect_with_history_succeeds(monkeypatch):
    """Disconnecting and reconnecting account A preserves its provenance."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-history-reconnect@example.com")
    context = _request_context(user, bearer=True)
    connection = _create_connection_with_tokens(user)
    activity = _create_historical_activity(
        connection,
        account="provider-user",
    )
    assert _disconnect(context).errors is None
    state = _begin_state(context)
    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        lambda _: _token_pair("provider-user"),
    )

    result = _complete_authorization(context, code="code-a", state=state)

    assert result.errors is None
    connection.refresh_from_db()
    assert connection.is_connected is True
    assert connection.provider_account_id == "provider-user"
    assert GarminActivity.objects.filter(pk=activity.pk).exists()


def test_account_switch_without_history_is_allowed_and_resets_sync_metadata(
    monkeypatch,
):
    """A connection without provenance may transactionally switch accounts."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-no-history-switch@example.com")
    context = _request_context(user, bearer=True)
    connection = _create_connection_with_tokens(user)
    connection.last_synced_at = timezone.now()
    connection.last_sync_summary = {"imported": 4}
    connection.save(update_fields=["last_synced_at", "last_sync_summary"])
    state = _begin_state(context)
    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        lambda _: _token_pair("provider-account-b"),
    )

    result = _complete_authorization(context, code="code-b", state=state)

    assert result.errors is None
    connection.refresh_from_db()
    assert connection.provider_account_id == "provider-account-b"
    assert connection.last_synced_at is None
    assert connection.last_sync_summary == {}
    assert connection.is_connected is True


def test_active_account_switch_with_history_is_rejected(monkeypatch):
    """An active connection cannot mix another account into historical rows."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-active-history-switch@example.com")
    context = _request_context(user, bearer=True)
    connection = _create_connection_with_tokens(user)
    activity = _create_historical_activity(
        connection,
        account="provider-user",
    )
    token_snapshot = (
        connection.access_token_encrypted,
        connection.refresh_token_encrypted,
        connection.connection_generation,
    )
    state = _begin_state(context)
    monkeypatch.setattr(
        schema_module,
        "exchange_code_for_tokens",
        lambda _: _token_pair("provider-account-b"),
    )

    result = _complete_authorization(context, code="code-b", state=state)

    assert result.errors is not None
    connection.refresh_from_db()
    assert connection.provider_account_id == "provider-user"
    assert connection.status == GarminConnection.Status.ACTIVE
    assert (
        connection.access_token_encrypted,
        connection.refresh_token_encrypted,
        connection.connection_generation,
    ) == (token_snapshot[0], token_snapshot[1], token_snapshot[2] + 1)
    assert GarminActivity.objects.filter(pk=activity.pk).exists()


def test_disconnected_status_retains_identity_only_internally(monkeypatch):
    """Public status stays disconnected without exposing identity or secrets."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-status-identity@example.com")
    context = _request_context(user, bearer=True)
    connection = _create_connection_with_tokens(user)

    assert _disconnect(context).errors is None
    result = schema_module.schema.execute_sync(
        """
            query {
                garminStatus {
                    connected
                    hasRefreshToken
                    lastSyncedAt
                    lastSyncSummary { imported }
                }
            }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data["garminStatus"] == {
        "connected": False,
        "hasRefreshToken": False,
        "lastSyncedAt": None,
        "lastSyncSummary": None,
    }
    connection.refresh_from_db()
    assert connection.provider_account_id == "provider-user"
    rendered = repr(result.data)
    assert "provider-user" not in rendered
    assert "access-token" not in rendered
    assert "refresh-token" not in rendered


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
