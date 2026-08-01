"""Garmin persistence models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models, router, transaction
from django.utils import timezone

from apps.libs.basemodel import BaseModel

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

GARMIN_PROVIDER = "garmin"
_TOKEN_ACCESS_SKEW = timedelta(seconds=30)


def _encryption_keys() -> list[bytes]:
    """Return validated Fernet keys for token encryption/decryption."""
    legacy_key = getattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEY", "")
    ring = getattr(settings, "GARMIN_TOKEN_ENCRYPTION_KEYS", "")

    configured_keys: list[str] = []
    if ring:
        configured_keys.extend(
            str(item).strip()
            for item in str(ring).split(",")
            if str(item).strip()
        )
    if legacy_key:
        configured_keys.append(str(legacy_key))

    if not configured_keys:
        raise ImproperlyConfigured("GARMIN_TOKEN_ENCRYPTION_KEY is required")

    keys: list[bytes] = []
    for key in configured_keys:
        raw_key = key.encode()
        Fernet(raw_key)
        if raw_key not in keys:
            keys.append(raw_key)
    return keys


def _encryption_key() -> bytes:
    """Return primary Fernet key."""
    return _encryption_keys()[0]


def ensure_token_encryption_available() -> None:
    """Validate encryption keys are present and parseable."""
    _encryption_keys()


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

    class Status(models.TextChoices):
        """Garmin connection lifecycle state."""

        ACTIVE = "active", "Active"
        DISCONNECTED = "disconnected", "Disconnected"

    user = models.OneToOneField(
        "users.User",
        on_delete=models.CASCADE,
        related_name="garmin_connection",
    )

    provider = models.CharField(max_length=32, default=GARMIN_PROVIDER)
    provider_account_id = models.CharField(
        max_length=255, blank=True, default=""
    )
    provider_scopes = models.JSONField(
        default=list,
        blank=True,
        help_text="OAuth scopes granted by Garmin.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status,
        default=Status.ACTIVE,
    )

    access_token_encrypted = models.TextField(blank=True, default="")
    refresh_token_encrypted = models.TextField(blank=True, default="")
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    connection_generation = models.PositiveBigIntegerField(default=1)
    authorization_placeholder = models.BooleanField(default=False)

    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_summary = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        """Return a non-sensitive connection label."""
        return f"Garmin connection for {self.user_id}"

    @property
    def is_active(self) -> bool:
        """Whether the link is currently active."""
        return self.status == self.Status.ACTIVE

    @property
    def has_refresh_token(self) -> bool:
        """Whether an encrypted refresh token exists."""
        try:
            return bool(self.refresh_token_encrypted)
        except ImproperlyConfigured:
            return False

    @property
    def has_unexpired_access_token(self) -> bool:
        """Whether an access token is available and still valid."""
        if not self.access_token_encrypted:
            return False
        if self.access_token_expires_at is None:
            return True
        return (
            self.access_token_expires_at > timezone.now() + _TOKEN_ACCESS_SKEW
        )

    @property
    def can_sync(self) -> bool:
        """Whether credentials can be used for sync attempts."""
        return bool(self.has_refresh_token or self.has_unexpired_access_token)

    @property
    def is_connected(self) -> bool:
        """Whether an active link with credentials exists."""
        return self.is_active and self.can_sync

    @staticmethod
    def _encrypt_value(value: str | None) -> str:
        """Encrypt a token string with the configured Fernet key."""
        ensure_token_encryption_available()
        if not value:
            return ""
        return Fernet(_encryption_key()).encrypt(value.encode()).decode()

    @staticmethod
    def _decrypt_value(value: str | None) -> str:
        """Decrypt a stored token value or fail with a stable message."""
        ensure_token_encryption_available()
        if not value:
            return ""
        for key in _encryption_keys():
            try:
                return Fernet(key).decrypt(value.encode()).decode()
            except InvalidToken:
                continue
        raise ValueError("Stored OAuth token is invalid")

    @property
    def access_token(self) -> str | None:
        """Return the decrypted access token if present."""
        return self._decrypt_value(self.access_token_encrypted) or None

    @property
    def refresh_token(self) -> str | None:
        """Return the decrypted refresh token if present."""
        return self._decrypt_value(self.refresh_token_encrypted) or None

    def set_tokens(
        self,
        token_pair: GarminTokenPair,
        *,
        expires_in: int,
    ) -> None:
        """Persist a fresh OAuth token pair for this connection."""
        self.access_token_encrypted = self._encrypt_value(
            token_pair.access_token
        )
        self.refresh_token_encrypted = self._encrypt_value(
            token_pair.refresh_token
        )
        self.access_token_expires_at = timezone.now() + timedelta(
            seconds=expires_in
        )

        if token_pair.provider_account_id is not None:
            self.provider_account_id = token_pair.provider_account_id
        if token_pair.scope is not None:
            self.provider_scopes = (
                token_pair.scope.split() if token_pair.scope.strip() else []
            )

        self.status = self.Status.ACTIVE
        self.authorization_placeholder = False
        self.connection_generation += 1

    def clear_tokens(self) -> None:
        """Drop all secrets and derived fields from this connection."""
        # Empty strings intentionally erase encrypted credentials.
        self.access_token_encrypted = ""  # nosec B105
        self.refresh_token_encrypted = ""  # nosec B105
        self.access_token_expires_at = None
        self.provider_scopes = []
        self.provider_account_id = ""
        self.last_synced_at = None
        self.last_sync_summary = {}
        self.status = self.Status.DISCONNECTED
        self.authorization_placeholder = False
        self.connection_generation += 1

    def clean(self) -> None:
        """Validate owner relationships for direct DB writes."""
        if self.id is None:
            return
        for activity in self.activities.all():
            if (
                activity.day is not None
                and activity.day.plan.user_id != self.user_id
            ):
                raise ValidationError(
                    "Garmin activity day must belong to the same user"
                )
            if activity.exercise is not None and (
                activity.exercise.day.plan.user_id != self.user_id
            ):
                raise ValidationError(
                    "Garmin exercise must belong to the same user"
                )


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
    def prune_expired(
        cls,
        *,
        now,
        user: "AbstractUser",
        provider: str,
        retention_seconds: int = 3600,
        using: str | None = None,
    ) -> None:
        """Delete stale rows and bound operational table growth."""
        if using is None:
            using = router.db_for_write(cls)

        cls.objects.using(using).filter(
            user=user,
            provider=provider,
            consumed_at__isnull=False,
            consumed_at__lt=timezone.now()
            - timedelta(seconds=retention_seconds),
        ).delete()
        cls.objects.using(using).filter(
            user=user, provider=provider, expires_at__lt=now
        ).delete()

    @classmethod
    def count_active(
        cls,
        *,
        user: "AbstractUser",
        provider: str,
        now,
        using: str | None = None,
    ) -> int:
        """Count unconsumed, unexpired state rows for a user/provider."""
        if using is None:
            using = router.db_for_write(cls)

        return (
            cls.objects.using(using)
            .filter(
                user=user,
                provider=provider,
                consumed_at__isnull=True,
                expires_at__gt=now,
            )
            .count()
        )

    @classmethod
    def create_for_user(
        cls,
        user: "AbstractUser",
        raw_state: str,
        *,
        provider: str,
        expires_at,
        using: str | None = None,
    ) -> "GarminOAuthState":
        """Create and persist a hash-only OAuth state row."""
        if using is None:
            using = router.db_for_write(cls)
        state_hash = cls.hash_state(raw_state)
        with transaction.atomic(using=using):
            return cls.objects.using(using).create(
                user=user,
                provider=provider,
                state_hash=state_hash,
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
            using = router.db_for_write(cls)

        now = timezone.now()
        with transaction.atomic(using=using):
            state_hash = cls.hash_state(raw_state)
            state = (
                cls.objects.using(using)
                .select_for_update(of=("self",))
                .get(
                    user=user,
                    provider=provider,
                    state_hash=state_hash,
                )
            )
            if state.expires_at <= now:
                raise ValueError("OAuth state is expired")
            if state.consumed_at is not None:
                raise ValueError("OAuth state is invalid or expired")

            updated = (
                cls.objects.using(using)
                .filter(pk=state.pk)
                .update(consumed_at=now)
            )
            if not updated:
                raise ValueError("OAuth state is invalid or expired")
            state.refresh_from_db(fields=["consumed_at"], using=using)
            return state


class GarminActivity(BaseModel):
    """Imported Garmin activity with deterministic provenance row.

    Uses a dedupe key to avoid duplicates.
    """

    connection = models.ForeignKey(
        GarminConnection,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    provider_activity_id = models.CharField(max_length=255)
    provider_activity_type = models.CharField(max_length=64)
    provider_account_id = models.CharField(
        max_length=255, blank=True, default=""
    )
    provider_local_started_date = models.DateField(blank=True, null=True)
    provider_local_started_time = models.TimeField(blank=True, null=True)
    provider_timezone_offset_minutes = models.SmallIntegerField(default=0)

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
    pending_reconciliation_reason = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    pending_reconciliation = models.BooleanField(
        default=False,
        help_text="Whether day resolution is still pending.",
    )

    exercise = models.OneToOneField(
        "exercises.Exercise",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="garmin_activity",
    )

    class Meta:
        unique_together = [
            ("connection", "provider_account_id", "provider_activity_id"),
        ]
        indexes = [
            models.Index(fields=["connection", "provider_activity_id"]),
            models.Index(fields=["day"]),
            models.Index(fields=["provider_account_id"]),
            models.Index(fields=["connection", "pending_reconciliation"]),
        ]

    def clean(self) -> None:
        """Validate owning user integrity between connection and links."""
        day = self.day
        exercise = self.exercise
        if (
            self.connection_id
            and day is not None
            and day.plan.user_id != self.connection.user_id
        ):
            raise ValidationError(
                "Garmin activity day must belong to the same user"
            )
        if self.connection_id and exercise is not None and exercise.day_id:
            if exercise.day.plan.user_id != self.connection.user_id:
                raise ValidationError(
                    "Garmin activity exercise must belong to the same user"
                )
