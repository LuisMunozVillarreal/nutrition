"""Garmin persistence models.

This module stores OAuth credentials and per-connection import provenance without
persisting raw OAuth state or private activity payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction
from django.utils import timezone

from apps.libs.basemodel import BaseModel

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

GARMIN_PROVIDER = "garmin"


def _encryption_key() -> bytes:
    """Return the configured Fernet key for token encryption.

    Returns:
        bytes: encrypted key bytes.

    Raises:
        ImproperlyConfigured: when the key is missing or invalid.
    """
    raw_key = getattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEY", "")
    if not raw_key:
        raise ImproperlyConfigured("GARMIN_TOKEN_ENCRYPTION_KEY is required")

    if isinstance(raw_key, str):
        raw_key = raw_key.encode()

    Fernet(raw_key)
    return raw_key


@dataclass(frozen=True)
class GarminTokenPair:
    """Normalized OAuth token pair payload."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    provider_account_id: str | None
    scope: str | None


class GarminConnection(BaseModel):
    """Per-user encrypted Garmin OAuth credentials and metadata."""

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="garmin_connection",
    )

    provider = models.CharField(max_length=32, default=GARMIN_PROVIDER)
    provider_account_id = models.CharField(max_length=255, blank=True, default="")
    provider_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="OAuth scopes granted by Garmin.",
    )

    access_token_encrypted = models.TextField(blank=True, default="")
    refresh_token_encrypted = models.TextField(blank=True, default="")
    access_token_expires_at = models.DateTimeField(null=True, blank=True)

    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_summary = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"Garmin connection for {self.user_id}"

    @property
    def has_refresh_token(self) -> bool:
        """Whether an encrypted refresh token exists."""
        return bool(self.refresh_token_encrypted)

    @property
    def is_connected(self) -> bool:
        """Whether a usable access token is currently available."""
        if not self.access_token_encrypted:
            return False
        if self.access_token_expires_at is None:
            return True
        return self.access_token_expires_at > timezone.now()

    @staticmethod
    def _encrypt_value(value: str | None) -> str:
        """Encrypt a token string with the configured Fernet key."""
        if not value:
            return ""
        return Fernet(_encryption_key()).encrypt(value.encode()).decode()

    @staticmethod
    def _decrypt_value(value: str | None) -> str:
        """Decrypt a stored token value.

        Raises:
            ValueError: when decryption fails.
        """
        if not value:
            return ""
        try:
            return Fernet(_encryption_key()).decrypt(value.encode()).decode()
        except (InvalidToken, ValueError) as exc:
            raise ValueError("Stored OAuth token is invalid") from exc

    @property
    def access_token(self) -> str | None:
        """Return the decrypted access token if present."""
        value = self._decrypt_value(self.access_token_encrypted)
        return value or None

    @property
    def refresh_token(self) -> str | None:
        """Return the decrypted refresh token if present."""
        value = self._decrypt_value(self.refresh_token_encrypted)
        return value or None

    def set_tokens(self, token_pair: GarminTokenPair, *, expires_in: int) -> None:
        """Persist a fresh OAuth token pair on this connection."""
        self.access_token_encrypted = self._encrypt_value(token_pair.access_token)
        self.refresh_token_encrypted = self._encrypt_value(token_pair.refresh_token)
        self.access_token_expires_at = timezone.now() + timezone.timedelta(
            seconds=max(int(expires_in), 0)
        )
        self.provider_account_id = token_pair.provider_account_id or ""

        if token_pair.scope:
            self.provider_scopes = token_pair.scope.split()
        else:
            self.provider_scopes = []

        self.last_synced_at = None

    def clear_tokens(self) -> None:
        """Drop all secrets and derived fields from this connection."""
        self.access_token_encrypted = ""
        self.refresh_token_encrypted = ""
        self.access_token_expires_at = None
        self.provider_scopes = []
        self.provider_account_id = ""
        self.last_synced_at = None
        self.last_sync_summary = {}

    def clear_activity_link(self, *fields: str) -> None:
        """No-op compatibility helper."""
        self.save(update_fields=list(fields) if fields else None)


class GarminOAuthState(BaseModel):
    """OAuth state row with only hashed state payload persisted."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="garmin_oauth_states",
    )
    provider = models.CharField(max_length=32, default=GARMIN_PROVIDER)
    state_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "provider"]),
            models.Index(fields=["expires_at"]),
        ]

    @property
    def is_valid(self) -> bool:
        """Whether the state can be used for an OAuth exchange."""
        return self.consumed_at is None and self.expires_at > timezone.now()

    @staticmethod
    def hash_state(raw_state: str) -> str:
        """Return a non-reversible hash for raw OAuth state."""
        import hashlib

        return hashlib.sha256(raw_state.encode()).hexdigest()

    @classmethod
    def create_for_user(
        cls,
        user: "AbstractUser",
        raw_state: str,
        *,
        provider: str,
        expires_at,
    ) -> "GarminOAuthState":
        """Create and persist a hash-only OAuth state row."""
        return cls.objects.create(
            user=user,
            provider=provider,
            state_hash=cls.hash_state(raw_state),
            expires_at=expires_at,
        )

    @classmethod
    def consume_for_user(
        cls,
        user: "AbstractUser",
        raw_state: str,
        *,
        provider: str,
        using: str | None = None,
    ) -> "GarminOAuthState":
        """Consume a state row for the user and provider, one-time only."""
        if using is None:
            from django.db import router

            using = router.db_for_write(cls)

        with transaction.atomic(using=using):
            state = (
                cls.objects.using(using)
                .select_for_update(of=("self",))
                .get(user=user, provider=provider, state_hash=cls.hash_state(raw_state))
            )
            if not state.is_valid:
                raise ValueError("OAuth state is invalid or expired")
            if state.expires_at <= timezone.now():
                raise ValueError("OAuth state is expired")

            state.consumed_at = timezone.now()
            state.save(update_fields=["consumed_at"])
            return state


class GarminActivity(BaseModel):
    """Imported Garmin activity with deterministic provenance row and dedupe key."""

    connection = models.ForeignKey(
        GarminConnection,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    provider_activity_id = models.CharField(max_length=255)
    provider_activity_type = models.CharField(max_length=64)
    provider_account_id = models.CharField(max_length=255, blank=True, default="")

    day = models.ForeignKey(
        "plans.Day",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="garmin_activities",
    )
    started_at = models.DateTimeField()
    kcals = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()
    distance = models.DecimalField(max_digits=10, decimal_places=2)

    exercise = models.OneToOneField(
        "exercises.Exercise",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="garmin_activity",
    )

    class Meta:
        unique_together = [
            ("connection", "provider_activity_id"),
        ]
        indexes = [
            models.Index(fields=["connection", "provider_activity_id"]),
            models.Index(fields=["day"]),
        ]
