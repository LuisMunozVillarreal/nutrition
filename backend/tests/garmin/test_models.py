"""Garmin model persistence and crypto/state tests."""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.garmin.models import (
    GarminActivity,
    GarminConnection,
    GarminOAuthState,
)
from apps.garmin.services import GarminTokenPair
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan

User = get_user_model()


def _set_encryption_key(
    monkeypatch: pytest.MonkeyPatch, *, value: str | None = None
) -> str:
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


def _create_user_with_day(email: str):
    user = _create_user(email)
    measurement = Measurement.objects.create(
        user=user,
        weight=Decimal("80.0"),
        body_fat_perc=Decimal("20.0"),
    )
    plan = WeekPlan.objects.create(
        user=user,
        measurement=measurement,
        start_date=date.today(),
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=500,
    )
    day = Day.objects.filter(plan=plan).first()
    assert day is not None
    return user, day


def _create_provider_activity(connection, day):
    exercise = Exercise.objects.create(
        day=day,
        time=time(9),
        type=Exercise.EXERCISE_CYCLE,
        kcals=100,
        duration=timedelta(minutes=20),
        distance=Decimal("5.00"),
    )
    activity = GarminActivity.objects.create(
        connection=connection,
        provider_activity_id="deletion-boundary",
        provider_activity_type="cycle",
        day=day,
        exercise=exercise,
        started_at=timezone.now(),
        kcals=100,
        duration_seconds=1200,
        distance=Decimal("5.00"),
    )
    return activity, exercise


def test_direct_connection_delete_is_protected_from_orphaning_provider_data():
    """Deleting a connection directly must preserve its provenance and exercise."""
    user, day = _create_user_with_day(
        "connection-delete-protected@example.com"
    )
    connection = GarminConnection.objects.create(user=user)
    activity, exercise = _create_provider_activity(connection, day)

    with pytest.raises(ProtectedError, match="Disconnect Garmin instead"):
        connection.delete()

    assert GarminConnection.objects.filter(pk=connection.pk).exists()
    assert GarminActivity.objects.filter(pk=activity.pk).exists()
    assert Exercise.objects.filter(pk=exercise.pk).exists()


def test_user_delete_cascades_connection_and_provider_data_without_cross_user_loss():
    """Account deletion remains complete while unrelated users remain untouched."""
    user, day = _create_user_with_day("connection-user-cascade@example.com")
    connection = GarminConnection.objects.create(user=user)
    activity, exercise = _create_provider_activity(connection, day)
    other_user, other_day = _create_user_with_day(
        "connection-user-cascade-other@example.com"
    )
    other_exercise = Exercise.objects.create(
        day=other_day,
        time=time(10),
        type=Exercise.EXERCISE_WALK,
        kcals=50,
    )

    user.delete()

    assert not GarminConnection.objects.filter(pk=connection.pk).exists()
    assert not GarminActivity.objects.filter(pk=activity.pk).exists()
    assert not Exercise.objects.filter(pk=exercise.pk).exists()
    assert User.objects.filter(pk=other_user.pk).exists()
    assert Exercise.objects.filter(pk=other_exercise.pk).exists()


def test_state_hash_is_sha256_hex_and_owner_bound(monkeypatch):
    """The OAuth state must be stored as SHA-256 only."""
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
    """Store access and refresh tokens encrypted.

    Decrypt them only through the model accessors.
    """
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


def test_clear_tokens_preserves_provider_identity_but_erases_secrets(
    monkeypatch,
):
    """Disconnect metadata retains identity without retaining credentials."""
    _set_encryption_key(monkeypatch)
    user = _create_user("connection-clear-identity@example.com")
    connection = GarminConnection.objects.create(user=user)
    token_pair = GarminTokenPair(
        access_token="access-plain",
        refresh_token="refresh-plain",
        expires_in=3600,
        scope="read write",
        provider_account_id="provider-account-a",
    )
    connection.set_tokens(token_pair, expires_in=token_pair.expires_in)

    connection.clear_tokens()

    assert connection.provider_account_id == "provider-account-a"
    assert connection.access_token_encrypted == ""
    assert connection.refresh_token_encrypted == ""
    assert connection.provider_scopes == []
    assert connection.status == GarminConnection.Status.DISCONNECTED
    assert connection.is_connected is False


def test_connection_tokens_fail_gracefully_on_wrong_encryption_key(
    monkeypatch,
):
    """Corrupting encryption key must fail token read validation."""
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


def test_connection_primary_keyring_key_is_used_for_new_writes(monkeypatch):
    """Keyring-first ordering should make its first key authoritative."""
    ring_key = Fernet.generate_key().decode()
    legacy_key = Fernet.generate_key().decode()

    monkeypatch.setattr(
        settings, "GARMIN_TOKEN_ENCRYPTION_KEYS", f"{ring_key}"
    )
    monkeypatch.setattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEY", legacy_key)

    user = _create_user("connection-keyring-primary@example.com")
    connection = GarminConnection.objects.create(user=user)

    token_pair = GarminTokenPair(
        access_token="rotated-access",
        refresh_token="refresh-token",
        expires_in=3600,
        scope=None,
        provider_account_id="provider-id",
    )
    connection.set_tokens(token_pair, expires_in=token_pair.expires_in)
    connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_scopes",
            "provider_account_id",
            "connection_generation",
        ]
    )

    decrypted = Fernet(ring_key.encode()).decrypt(
        connection.access_token_encrypted.encode()
    )
    assert decrypted == b"rotated-access"
    with pytest.raises(InvalidToken):
        Fernet(legacy_key.encode()).decrypt(
            connection.access_token_encrypted.encode()
        )


def test_connection_keyring_and_legacy_decrypt_old_ciphertext(monkeypatch):
    """Legacy key must remain a valid decrypt fallback."""
    legacy_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    monkeypatch.setattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEY", legacy_key)
    monkeypatch.setattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEYS", "")

    user = _create_user("connection-keyring-rotation@example.com")
    connection = GarminConnection.objects.create(user=user)

    connection.set_tokens(
        GarminTokenPair(
            access_token="legacy-access",
            refresh_token="legacy-refresh",
            expires_in=3600,
            scope=None,
            provider_account_id="provider-id",
        ),
        expires_in=3600,
    )
    connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_scopes",
            "provider_account_id",
            "connection_generation",
        ]
    )
    legacy_ciphertext = connection.access_token_encrypted

    monkeypatch.setattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEYS", new_key)

    connection.set_tokens(
        GarminTokenPair(
            access_token="rotated-access",
            refresh_token="rotated-refresh",
            expires_in=3600,
            scope=None,
            provider_account_id="provider-id",
        ),
        expires_in=3600,
    )
    connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_scopes",
            "provider_account_id",
            "connection_generation",
        ]
    )

    # New writes are encrypted with the keyring primary key.
    assert (
        Fernet(new_key.encode()).decrypt(
            connection.access_token_encrypted.encode()
        )
        == b"rotated-access"
    )
    with pytest.raises(InvalidToken):
        Fernet(new_key.encode()).decrypt(legacy_ciphertext.encode())

    # Existing ciphertext still decrypts via legacy fallback.
    assert (
        Fernet(legacy_key.encode()).decrypt(legacy_ciphertext.encode())
        == b"legacy-access"
    )
