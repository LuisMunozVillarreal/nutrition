"""GraphQL coverage for Garmin auth and isolation boundaries."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.garmin.services import GarminSyncSummary, GarminTokenPair
from apps.garmin.models import GarminConnection
import config.schema as schema_module

User = get_user_model()


def _configure_garmin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GARMIN_ENABLED", True)
    monkeypatch.setattr(settings, "GARMIN_CLIENT_ID", "garmin-client-id")
    monkeypatch.setattr(settings, "GARMIN_CLIENT_SECRET", "garmin-secret")
    monkeypatch.setattr(
        settings, "GARMIN_AUTHORIZATION_URL", "https://garmin.example.com/auth"
    )
    monkeypatch.setattr(settings, "GARMIN_TOKEN_URL", "https://garmin.example.com/token")
    monkeypatch.setattr(
        settings, "GARMIN_ACTIVITIES_URL", "https://garmin.example.com/activities"
    )
    monkeypatch.setattr(settings, "GARMIN_CALLBACK_URL", "https://app.example.com/callback")
    monkeypatch.setattr(settings, "GARMIN_SCOPES", "read write")
    monkeypatch.setattr(settings, "GARMIN_REQUEST_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_PAGES", 3)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITIES_LIMIT", 100)
    monkeypatch.setattr(settings, "GARMIN_STATE_TTL_SECONDS", 300)
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


def _request_context(user):
    request = type("Request", (), {"user": user})()
    return type("Context", (), {"request": request})()


def test_begin_garmin_authorization_requires_authentication():
    """Unauthorized callers cannot start Garmin authorization flow."""
    result = schema_module.schema.execute_sync(
        """
            mutation {
                beginGarminAuthorization {
                    authorizationUrl
                    state
                    expiresAt
                }
            }
        """
    )

    assert result.errors is not None
    assert "Authentication required" in result.errors[0].message


def test_complete_garmin_authorization_replays_state_once(monkeypatch):
    """State can be consumed one time and then cannot be replayed."""
    _configure_garmin(monkeypatch)
    user = _create_user("garmin-replay@example.com")
    context = _request_context(user)

    monkeypatch.setattr(
        "apps.garmin.services.exchange_code_for_tokens",
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


def test_sync_mutation_isolation_for_authenticated_user(monkeypatch):
    """Garmin sync mutation must run against the caller's own connection."""
    _configure_garmin(monkeypatch)
    owner = _create_user("garmin-owner@example.com")
    stranger = _create_user("garmin-stranger@example.com")

    owner_connection = GarminConnection.objects.create(user=owner)
    owner_connection.set_tokens(
        GarminTokenPair(
            access_token="owner-access",
            refresh_token="owner-refresh",
            expires_in=3600,
            provider_account_id="provider-user",
            scope="read",
        ),
        expires_in=3600,
    )
    owner_connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_scopes",
            "provider_account_id",
        ]
    )

    GarminConnection.objects.create(user=stranger)

    def _fake_sync(connection):
        assert connection == owner_connection
        return GarminSyncSummary(imported=1, duplicates=0, unsupported=0, invalid=0)

    monkeypatch.setattr(schema_module, "sync_connection", _fake_sync)

    result = schema_module.schema.execute_sync(
        """
            mutation {
                syncGarmin {
                    imported
                    duplicates
                    unsupported
                    invalid
                }
            }
        """,
        context_value=_request_context(owner),
    )

    assert result.errors is None
    assert result.data["syncGarmin"] == {
        "imported": 1,
        "duplicates": 0,
        "unsupported": 0,
        "invalid": 0,
    }
