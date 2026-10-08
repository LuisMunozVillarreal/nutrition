"""Persistence for paired health-data companion devices."""

# Model helpers document credential behavior without repeating type signatures.
# pylint: disable=missing-param-doc,missing-return-doc,missing-raises-doc

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Self

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.libs.basemodel import BaseModel

if TYPE_CHECKING:
    from apps.users.models import User

PAIRING_CODE_TTL = timedelta(minutes=10)
PAIRING_CODE_EMISSION_INTERVAL = timedelta(seconds=30)
PAIRING_CODE_DIGITS = 12
DEVICE_TOKEN_TTL = timedelta(days=180)
MAX_ACTIVE_DEVICES_PER_USER = 10
# Public format prefix, not a credential.
TOKEN_PREFIX = "nhs_"  # nosec B105


def _keyed_digest(value: str, key_value: str) -> str:
    """Return a keyed digest without persisting the credential itself."""
    return hmac.new(
        key_value.encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def _pairing_digest(value: str) -> str:
    """Digest a short-lived pairing code with the application secret."""
    return _keyed_digest(value, str(settings.SECRET_KEY))


def _token_digest(value: str, pepper: str | None = None) -> str:
    """Digest a durable token with its independently rotatable pepper."""
    return _keyed_digest(
        value,
        pepper or str(settings.HEALTH_SYNC_TOKEN_PEPPER),
    )


def device_token_expiry() -> datetime:
    """Return the expiry for a newly issued device credential."""
    return timezone.now() + DEVICE_TOKEN_TTL


class HealthSyncPairingCode(BaseModel):
    """Single-use, short-lived code used to pair an Android companion."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="health_sync_pairing_codes",
    )
    code_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user: "User") -> tuple[str, "HealthSyncPairingCode"]:
        """Issue a short-lived numeric pairing code, returning plaintext once."""
        for _attempt in range(10):
            number = secrets.randbelow(10**PAIRING_CODE_DIGITS)
            raw_code = f"{number:0{PAIRING_CODE_DIGITS}d}"
            try:
                with transaction.atomic():
                    pairing = cls.objects.create(
                        user=user,
                        code_hash=_pairing_digest(raw_code),
                        expires_at=timezone.now() + PAIRING_CODE_TTL,
                    )
                return raw_code, pairing
            except IntegrityError:
                continue
        raise RuntimeError("Could not generate a unique pairing code")

    @classmethod
    def consume(cls, raw_code: str) -> "HealthSyncPairingCode":
        """Atomically consume a valid code or raise a stable error."""
        with transaction.atomic():
            try:
                pairing = cls.objects.select_for_update().get(
                    code_hash=_pairing_digest(raw_code),
                    consumed_at=None,
                    expires_at__gt=timezone.now(),
                )
            except cls.DoesNotExist as exc:
                raise ValueError("Pairing code is invalid or expired") from exc
            pairing.consumed_at = timezone.now()
            pairing.save(update_fields=["consumed_at", "updated_at"])
            return pairing


class HealthSyncDevice(BaseModel):
    """Revocable scoped credential for a health-data companion device."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="health_sync_devices",
    )
    name = models.CharField(max_length=120)
    token_prefix = models.CharField(max_length=16, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=device_token_expiry)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user: "User", name: str) -> tuple[str, "HealthSyncDevice"]:
        """Create a high-entropy token and return its plaintext exactly once."""
        with transaction.atomic():
            locked_user = (
                type(user).objects.select_for_update().get(pk=user.pk)
            )
            now = timezone.now()
            cls.objects.filter(user=locked_user, expires_at__lte=now).delete()
            active_count = cls.objects.filter(
                user=locked_user,
                revoked_at=None,
                expires_at__gt=now,
            ).count()
            if active_count >= MAX_ACTIVE_DEVICES_PER_USER:
                raise ValueError("Too many active health-sync devices")
            raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
            device = cls.objects.create(
                user=locked_user,
                name=name,
                token_prefix=raw_token[:12],
                token_hash=_token_digest(raw_token),
            )
        return raw_token, device

    @classmethod
    def authenticate(cls, raw_token: str) -> "HealthSyncDevice | None":
        """Resolve an active device credential using constant-time comparison."""
        if not raw_token.startswith(TOKEN_PREFIX):
            return None
        devices = list(
            cls.objects.filter(
                token_prefix=raw_token[:12],
                user__is_active=True,
                revoked_at=None,
                expires_at__gt=timezone.now(),
            ).exclude(auth_grant__access_expires_at__lte=timezone.now())
        )
        peppers = [
            str(settings.HEALTH_SYNC_TOKEN_PEPPER),
            *[
                str(value)
                for value in settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS
            ],
        ]
        matched: Self | None = None
        for pepper in peppers:
            candidate = _token_digest(raw_token, pepper)
            for device in devices:
                if hmac.compare_digest(device.token_hash, candidate):
                    matched = device
        if matched is None:
            return None

        device = matched
        current_hash = _token_digest(raw_token)
        now = timezone.now()
        # Compare-and-swap on the device row, not an unconditional stale save.
        # Another authenticator may already have migrated this same credential;
        # a refresh or revocation must instead win and reject this stale request.
        if not cls.objects.filter(
            pk=device.pk,
            token_hash__in=(device.token_hash, current_hash),
            revoked_at=None,
            expires_at__gt=now,
        ).update(token_hash=current_hash, last_seen_at=now, updated_at=now):
            return None
        device.token_hash = current_hash
        device.last_seen_at = now
        device.updated_at = now
        return device

    def mark_sync_success(self) -> None:
        """Record a validated upload that processed at least one owned day."""
        self.last_success_at = timezone.now()
        self.save(update_fields=["last_success_at", "updated_at"])

    def revoke(self) -> None:
        """Revoke this device credential."""
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at", "updated_at"])


class HealthSyncAuthorization(BaseModel):
    """Bind a single-use browser authorization to its initiating app."""

    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64, unique=True)
    challenge = models.CharField(max_length=43)
    redirect_uri = models.CharField(max_length=120)
    issuer = models.CharField(max_length=255)
    device_name = models.CharField(max_length=120)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)


class HealthSyncGrant(BaseModel):
    """Keep only hashed renewal credentials and bounded retry metadata."""

    device = models.OneToOneField(
        HealthSyncDevice, on_delete=models.CASCADE, related_name="auth_grant"
    )
    access_expires_at = models.DateTimeField()
    refresh_hash = models.CharField(max_length=64, unique=True)
    previous_refresh_hash = models.CharField(max_length=64, blank=True)
    issuer = models.CharField(max_length=255)


class HealthSyncSpentRefresh(BaseModel):
    """Retain consumed credential digests until their device family is deleted."""

    grant = models.ForeignKey(
        HealthSyncGrant,
        on_delete=models.CASCADE,
        related_name="spent_refreshes",
    )
    token_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["grant", "token_hash"],
                name="unique_spent_refresh_per_grant",
            )
        ]


class StepImport(BaseModel):
    """Provenance and freshness metadata for an imported daily step total."""

    SOURCE_HEALTH_CONNECT = "health_connect"

    day_steps = models.OneToOneField(
        "exercises.DaySteps",
        on_delete=models.CASCADE,
        related_name="step_import",
    )
    device = models.ForeignKey(
        HealthSyncDevice,
        on_delete=models.SET_NULL,
        null=True,
        related_name="step_imports",
    )
    source = models.CharField(max_length=32, default=SOURCE_HEALTH_CONNECT)
    observed_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["source", "observed_at"])]


class StepSyncWatermark(BaseModel):
    """Latest accepted device observation retained across manual deletion."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="step_sync_watermarks",
    )
    date = models.DateField()
    observed_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                name="unique_step_sync_watermark_per_user_date",
            )
        ]
