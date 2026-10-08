"""Browser consent and PKCE exchange for the first-party Android companion."""

# Public handlers share deliberately generic errors and concise contract docs.
# pylint: disable=missing-param-doc,missing-return-doc,missing-raises-doc

import base64
import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.health_sync.models import (
    HealthSyncAuthorization,
    HealthSyncDevice,
    HealthSyncGrant,
    HealthSyncSpentRefresh,
    _pairing_digest,
    _token_digest,
    device_token_expiry,
)
from apps.health_sync.views import _json_body, _pairing_rate_limited
from apps.users.models import User
from config.middleware import authenticated_request_user

REDIRECTS = frozenset(
    {
        "com.nutrition.healthsync:/oauth2redirect",
        "com.nutrition.healthsync.testing:/oauth2redirect",
    }
)
OPAQUE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z")
ACCESS_TTL = timedelta(minutes=15)


def _response(body: dict[str, Any], status: int = 200) -> JsonResponse:
    """Prevent credential responses from entering shared caches."""
    response = JsonResponse(body, status=status)
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _payload(request: HttpRequest) -> dict[str, Any]:
    """Require a bounded object tied to this exact HTTPS origin."""
    payload = _json_body(request)
    if (
        not isinstance(payload, dict)
        or not request.is_secure()
        or payload.get("issuer") != f"https://{request.get_host()}"
    ):
        raise ValueError("Invalid request")
    return payload


@csrf_exempt
@require_POST
def authorize_device(request: HttpRequest) -> JsonResponse:
    """Accept explicit same-origin browser consent with an account bearer JWT."""
    # Never accept cookie-only authentication on this CSRF-exempt endpoint.
    if not request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer "):
        return _response({"error": "Authentication required"}, 401)
    user = authenticated_request_user(request)
    if user is None:
        return _response({"error": "Authentication required"}, 401)
    if _pairing_rate_limited(request):
        return _response({"error": "Too many requests"}, 429)
    try:
        payload = _payload(request)
        if not all(
            isinstance(payload.get(key), str)
            for key in (
                "redirect_uri",
                "code_challenge_method",
                "code_challenge",
                "state",
                "device_name",
            )
        ):
            raise ValueError("Invalid request")
        if (
            request.headers.get("Origin") != payload["issuer"]
            or payload.get("redirect_uri") not in REDIRECTS
            or payload.get("code_challenge_method") != "S256"
            or not OPAQUE.fullmatch(str(payload.get("code_challenge", "")))
            or not OPAQUE.fullmatch(payload["state"])
        ):
            raise ValueError("Invalid request")
        if not 1 <= len(payload["device_name"].strip()) <= 120:
            raise ValueError("Invalid request")
        code = secrets.token_urlsafe(32)
        with transaction.atomic():
            type(user).objects.select_for_update().get(pk=user.pk)
            now = timezone.now()
            HealthSyncAuthorization.objects.filter(user=user).delete()
            HealthSyncAuthorization.objects.create(
                user=user,
                code_hash=_pairing_digest(code),
                challenge=payload["code_challenge"],
                redirect_uri=payload["redirect_uri"],
                issuer=payload["issuer"],
                device_name=payload["device_name"].strip(),
                expires_at=now + timedelta(minutes=5),
            )
        return _response({"code": code, "state": payload["state"]}, 201)
    except ValueError:
        return _response({"error": "Invalid authorization request"}, 400)


def _credentials(access: str, refresh: str) -> dict[str, Any]:
    """Describe only the narrowly scoped companion grant."""
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "scope": "health-sync:steps",
        "expires_in": int(ACCESS_TTL.total_seconds()),
    }


def _exchange(payload: dict[str, Any]) -> dict[str, Any]:
    """Atomically consume one code after validating the PKCE proof."""
    verifier = payload.get("code_verifier", "")
    if not isinstance(verifier, str) or not VERIFIER.fullmatch(verifier):
        raise ValueError("Invalid grant")
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )
    with transaction.atomic():
        # Resolve only the immutable owner before locking. Consent deletes codes
        # under the owner lock, so revalidate the authorization after waiting.
        candidate = HealthSyncAuthorization.objects.get(
            code_hash=_pairing_digest(str(payload.get("code", ""))),
            issuer=payload["issuer"],
        )
        user = User.objects.select_for_update().get(
            pk=candidate.user_id, is_active=True
        )
        authorization = HealthSyncAuthorization.objects.select_for_update(
            of=("self",)
        ).get(
            code_hash=_pairing_digest(str(payload.get("code", ""))),
            issuer=payload["issuer"],
            redirect_uri=payload.get("redirect_uri", ""),
            consumed_at=None,
            expires_at__gt=timezone.now(),
            user_id=user.pk,
        )
        if not hmac.compare_digest(challenge, authorization.challenge):
            raise ValueError("Invalid grant")
        authorization.consumed_at = timezone.now()
        authorization.save(update_fields=["consumed_at", "updated_at"])
        access, device = HealthSyncDevice.issue(
            authorization.user, authorization.device_name
        )
        refresh = secrets.token_urlsafe(32)
        HealthSyncGrant.objects.create(
            device=device,
            refresh_hash=_token_digest(refresh),
            issuer=payload["issuer"],
            access_expires_at=timezone.now() + ACCESS_TTL,
        )
        return _credentials(access, refresh)


def _token_hashes(token: str) -> dict[str, str]:
    """Map accepted digests to the pepper needed for identical retry output."""
    return {
        _token_digest(token, str(pepper)): str(pepper)
        for pepper in (
            settings.HEALTH_SYNC_TOKEN_PEPPER,
            *settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS,
        )
    }


def _spent_digest(token: str) -> str:
    """Fingerprint a high-entropy spent token independently of pepper rotation."""
    # These fingerprints only detect reuse; they can never authorize a refresh.
    return hashlib.sha256(
        ("spent-refresh:" + token).encode("ascii")
    ).hexdigest()


def _refresh(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Rotate atomically, allowing only the identical durable replacement retry."""
    old = payload.get("refresh_token", "")
    new = payload.get("next_refresh_token", "")
    if (
        not isinstance(old, str)
        or not isinstance(new, str)
        or not OPAQUE.fullmatch(old)
        or not OPAQUE.fullmatch(new)
        or old == new
    ):
        raise ValueError("Invalid grant")
    old_hashes, new_hashes = _token_hashes(old), _token_hashes(new)
    with transaction.atomic():
        candidate = HealthSyncGrant.objects.get(
            Q(refresh_hash__in=old_hashes)
            | Q(previous_refresh_hash__in=old_hashes)
            | Q(
                pk__in=HealthSyncSpentRefresh.objects.filter(
                    token_hash__in=(*old_hashes, _spent_digest(old))
                ).values("grant_id")
            ),
            issuer=payload["issuer"],
        )
        User.objects.select_for_update().get(
            pk=candidate.device.user_id, is_active=True
        )
        device = HealthSyncDevice.objects.select_for_update(of=("self",)).get(
            pk=candidate.device_id,
            revoked_at=None,
            expires_at__gt=timezone.now(),
            user__is_active=True,
        )
        grant = HealthSyncGrant.objects.select_for_update().get(
            pk=candidate.pk
        )
        if grant.refresh_hash in old_hashes:
            if (
                grant.previous_refresh_hash in new_hashes
                or grant.spent_refreshes.filter(
                    token_hash__in=(*new_hashes, _spent_digest(new))
                ).exists()
            ):
                raise ValueError("Invalid grant")
            # Keep every spent generation, including a predecessor created by
            # the older schema. The family locks serialize history and rotation.
            for digest in (_spent_digest(old), grant.previous_refresh_hash):
                if digest:
                    HealthSyncSpentRefresh.objects.get_or_create(
                        grant=grant, token_hash=digest
                    )
            grant.previous_refresh_hash = _token_digest(old)
            grant.refresh_hash = _token_digest(new)
        elif not (
            grant.previous_refresh_hash in old_hashes
            and grant.refresh_hash in new_hashes
        ):
            # A recognized spent token proposing a different successor signals
            # compromise. Return normally so the revocation is not rolled back.
            device.revoke()
            return None
        # A keyed PRF reproduces the access credential after a lost response;
        # neither the raw refresh nor the access token is stored server-side.
        # Keep retry hashes at their original pepper until an actual rotation:
        # changing them here would change the access credential on the next retry.
        access = "nhs_" + _token_digest(
            "access:" + new, new_hashes[grant.refresh_hash]
        )
        device.token_hash = _token_digest(access)
        device.token_prefix = access[:12]
        device.expires_at = device_token_expiry()
        device.save(
            update_fields=[
                "token_hash",
                "token_prefix",
                "expires_at",
                "updated_at",
            ]
        )
        grant.access_expires_at = timezone.now() + ACCESS_TTL
        grant.save(
            update_fields=[
                "refresh_hash",
                "previous_refresh_hash",
                "access_expires_at",
                "updated_at",
            ]
        )
        return _credentials(access, new)


@csrf_exempt
@require_POST
def revoke_device(request: HttpRequest) -> JsonResponse:
    """Revoke both credentials using the device's current renewal credential."""
    if _pairing_rate_limited(request):
        return _response({"error": "Too many requests"}, 429)
    try:
        payload = _payload(request)
        grant = HealthSyncGrant.objects.get(
            refresh_hash__in=_token_hashes(
                str(payload.get("refresh_token", ""))
            ),
            issuer=payload["issuer"],
        )
        # UPDATE serializes with refresh's device lock. Revocation is monotonic.
        HealthSyncDevice.objects.filter(pk=grant.device_id).update(
            revoked_at=timezone.now(), updated_at=timezone.now()
        )
        return _response({"revoked": True})
    except (ValueError, HealthSyncGrant.DoesNotExist):
        return _response({"error": "invalid_grant"}, 400)


@csrf_exempt
@require_POST
def exchange_token(request: HttpRequest) -> JsonResponse:
    """Exchange the one-time browser code without any account cookie access."""
    if _pairing_rate_limited(request):
        return _response({"error": "Too many requests"}, 429)
    try:
        payload = _payload(request)
        if payload.get("grant_type") == "authorization_code":
            return _response(_exchange(payload))
        if payload.get("grant_type") == "refresh_token":
            credentials = _refresh(payload)
            if credentials is None:
                return _response({"error": "invalid_grant"}, 400)
            return _response(credentials)
        raise ValueError("Invalid grant")
    except (
        ValueError,
        HealthSyncAuthorization.DoesNotExist,
        HealthSyncGrant.DoesNotExist,
        HealthSyncDevice.DoesNotExist,
        User.DoesNotExist,
    ):
        return _response({"error": "invalid_grant"}, 400)
