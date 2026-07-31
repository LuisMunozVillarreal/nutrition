"""Garmin model persistence and crypto/state tests."""

from datetime import timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
import pytest

from apps.garmin.models import GarminConnection, GarminOAuthState
from apps.garmin.services import GarminTokenPair

User = get_user_model()


def _set_encryption_key(monkeypatch: object, *, value: str | None = None) -> str:
    if value is None:
        value = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEY", value)
    return value


def _create_user(email: str):
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


def test_state_hash_is_sha256_hex_and_owner_bound(monkeypatch):
    """OAuth state must be stored as SHA-256 only."""
    user = _create_user("state-hash@example.com")
    state = "my-raw-state"

    token = GarminOAuthState.create_for_user(
        user=user,
        raw_state=state,
        provider="garmin",
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    assert token.state_hash == GarminOAuthState.hash_state(state)
    assert token.state_hash != state
    assert len(token.state_hash) == 64
    assert token.user_id == user.id


def test_state_is_consumed_once_and_checks_expiration(monkeypatch):
    """Consumed states must be single-use and reject replay or expiry."""
    user = _create_user("state-once@example.com")
    state = "replay-safe"

    GarminOAuthState.create_for_user(
        user=user,
        raw_state=state,
        provider="garmin",
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    first = GarminOAuthState.consume_for_user(
        user=user,
        raw_state=state,
        provider="garmin",
    )
    assert first.consumed_at is not None

    with pytest.raises(ValueError, match="OAuth state is invalid or expired"):
        GarminOAuthState.consume_for_user(
            user=user,
            raw_state=state,
            provider="garmin",
        )

    GarminOAuthState.create_for_user(
        user=user,
        raw_state="expired-state",
        provider="garmin",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="OAuth state is expired"):
        GarminOAuthState.consume_for_user(
            user=user,
            raw_state="expired-state",
            provider="garmin",
        )


def test_connection_tokens_are_encrypted_with_fernet(monkeypatch):
    """Access/refresh tokens must be stored encrypted and decrypted
    only through accessors."""
    _set_encryption_key(monkeypatch)
    user = _create_user("connection-tokens@example.com")

    connection = GarminConnection.objects.create(user=user)
    token_pair = GarminTokenPair(
        access_token="access-plain",
        refresh_token="refresh-plain",
        expires_in=3600,
        scope="read write",
        provider_account_id="provider-id",
    )
    connection.set_tokens(token_pair, expires_in=token_pair.expires_in)

    assert "access-plain" not in connection.access_token_encrypted
    assert "refresh-plain" not in connection.refresh_token_encrypted
    assert connection.access_token == "access-plain"
    assert connection.refresh_token == "refresh-plain"
    assert connection.provider_scopes == ["read", "write"]


def test_connection_tokens_fail_gracefully_on_wrong_encryption_key(monkeypatch):
    """Corrupting encryption key must fail token read validation deterministically."""
    _set_encryption_key(monkeypatch)
    user = _create_user("connection-key-rotation@example.com")

    connection = GarminConnection.objects.create(user=user)
    token_pair = GarminTokenPair(
        access_token="access-plain",
        refresh_token="refresh-plain",
        expires_in=3600,
        scope=None,
        provider_account_id=None,
    )
    connection.set_tokens(token_pair, expires_in=token_pair.expires_in)

    wrong_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEY", wrong_key)

    with pytest.raises(ValueError, match="Stored OAuth token is invalid"):
        _ = connection.access_token


def test_connection_token_access_blocked_when_key_is_missing(monkeypatch):
    """Missing encryption key must fail before any token use."""
    _set_encryption_key(monkeypatch, value="")
    user = _create_user("connection-key-missing@example.com")

    connection = GarminConnection(user=user)
    with pytest.raises(
        ImproperlyConfigured, match="GARMIN_TOKEN_ENCRYPTION_KEY is required"
    ):
        _ = connection.access_token
