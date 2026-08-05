"""HTTP endpoints consumed only by the Android Health Connect companion."""

# Django view signatures and response branches form the HTTP contract.
# pylint: disable=missing-param-doc,missing-return-doc

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.health_sync.models import (
    PAIRING_CODE_DIGITS,
    HealthSyncDevice,
    HealthSyncPairingCode,
)
from apps.health_sync.services import parse_records, sync_records

MAX_JSON_BODY_BYTES = 64 * 1024
PAIRING_ATTEMPTS_PER_IP = 20
PAIRING_ATTEMPT_WINDOW_SECONDS = 10 * 60
PAIRING_ATTEMPTS_GLOBAL = 500
PAIRING_GLOBAL_WINDOW_SECONDS = 60
UPLOAD_ATTEMPTS_PER_IP = 120
UPLOAD_ATTEMPTS_GLOBAL = 2_000
UPLOAD_WINDOW_SECONDS = 60


def _increment_rate_limit(key: str, limit: int, timeout: int) -> bool:
    """Increment a fixed-window cache counter and report whether it overflowed."""
    if cache.add(key, 1, timeout=timeout):
        return False
    try:
        return int(cache.incr(key)) > limit
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return False


def _client_address(request: HttpRequest) -> str:
    """Return a forwarded client only when the direct peer is explicitly trusted."""
    remote_addr = str(request.META.get("REMOTE_ADDR") or "unknown")
    trusted_proxy_count = int(settings.HEALTH_SYNC_TRUSTED_PROXY_COUNT)
    forwarded = [
        part.strip()
        for part in str(request.META.get("HTTP_X_FORWARDED_FOR") or "").split(
            ","
        )
        if part.strip()
    ]
    try:
        peer = ipaddress.ip_address(remote_addr)
        trusted_peer = any(
            peer in ipaddress.ip_network(cidr)
            for cidr in settings.HEALTH_SYNC_TRUSTED_PROXY_CIDRS
        )
    except ValueError:
        trusted_peer = False
    if trusted_peer and 0 < trusted_proxy_count <= len(forwarded):
        candidate = forwarded[-trusted_proxy_count]
        try:
            remote_addr = str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
    return remote_addr


def _private_digest(value: str) -> str:
    """Create a cache-safe keyed identifier without retaining raw addresses."""
    return hmac.new(
        str(settings.SECRET_KEY).encode(),
        value.encode(),
        hashlib.sha256,
    ).hexdigest()


def _pairing_rate_limited(request: HttpRequest) -> bool:
    """Bound public pairing attempts globally and by client address."""
    ip_digest = _private_digest(_client_address(request))
    global_limited = _increment_rate_limit(
        "health-sync:pair:global",
        PAIRING_ATTEMPTS_GLOBAL,
        PAIRING_GLOBAL_WINDOW_SECONDS,
    )
    ip_limited = _increment_rate_limit(
        f"health-sync:pair:ip:{ip_digest}",
        PAIRING_ATTEMPTS_PER_IP,
        PAIRING_ATTEMPT_WINDOW_SECONDS,
    )
    return global_limited or ip_limited


def _upload_ip_rate_limited(request: HttpRequest) -> bool:
    """Bound invalid and valid upload attempts before bearer lookup."""
    ip_digest = _private_digest(_client_address(request))
    global_limited = _increment_rate_limit(
        "health-sync:upload:global",
        UPLOAD_ATTEMPTS_GLOBAL,
        UPLOAD_WINDOW_SECONDS,
    )
    ip_limited = _increment_rate_limit(
        f"health-sync:upload:ip:{ip_digest}",
        UPLOAD_ATTEMPTS_PER_IP,
        UPLOAD_WINDOW_SECONDS,
    )
    return global_limited or ip_limited


def _device_upload_rate_limited(device: HealthSyncDevice) -> bool:
    """Bound writes from each authenticated companion credential."""
    return _increment_rate_limit(
        f"health-sync:upload:device:{device.pk}",
        int(settings.HEALTH_SYNC_UPLOADS_PER_DEVICE),
        UPLOAD_WINDOW_SECONDS,
    )


def _json_body(request: HttpRequest) -> Any:
    """Decode a request body or raise a stable validation error."""
    try:
        declared_size = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        declared_size = 0
    if declared_size > MAX_JSON_BODY_BYTES:
        raise ValueError("Request body is too large")
    body = request.body
    if len(body) > MAX_JSON_BODY_BYTES:
        raise ValueError("Request body is too large")
    try:
        return json.loads(body)
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        raise ValueError("Request body must be valid JSON") from exc


def _device_from_request(request: HttpRequest) -> HealthSyncDevice | None:
    """Authenticate a scoped companion bearer token."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return HealthSyncDevice.authenticate(parts[1])


@csrf_exempt
@require_POST
def pair_device(request: HttpRequest) -> JsonResponse:
    """Exchange a one-time pairing code for a scoped device token."""
    if _pairing_rate_limited(request):
        response = JsonResponse(
            {"error": "Too many pairing attempts"}, status=429
        )
        response["Retry-After"] = str(PAIRING_ATTEMPT_WINDOW_SECONDS)
        return response
    try:
        payload = _json_body(request)
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        code = payload.get("code")
        name = payload.get("device_name")
        if (
            not isinstance(code, str)
            or len(code) != PAIRING_CODE_DIGITS
            or not code.isdigit()
        ):
            raise ValueError("Pairing code is invalid or expired")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 120
        ):
            raise ValueError("device_name must contain 1 to 120 characters")
        with transaction.atomic():
            pairing = HealthSyncPairingCode.consume(code)
            raw_token, device = HealthSyncDevice.issue(
                user=pairing.user,
                name=name.strip(),
            )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "token": raw_token,
            "device_id": device.id,
            "device_name": device.name,
        },
        status=201,
    )


@csrf_exempt
@require_POST
def upload_steps(request: HttpRequest) -> JsonResponse:
    """Validate and import a bounded batch of daily Health Connect totals."""
    if _upload_ip_rate_limited(request):
        response = JsonResponse(
            {"error": "Too many upload attempts"}, status=429
        )
        response["Retry-After"] = str(UPLOAD_WINDOW_SECONDS)
        return response
    device = _device_from_request(request)
    if device is None:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if _device_upload_rate_limited(device):
        response = JsonResponse(
            {"error": "Too many upload attempts"}, status=429
        )
        response["Retry-After"] = str(UPLOAD_WINDOW_SECONDS)
        return response
    try:
        records = parse_records(_json_body(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    result = sync_records(device, records)
    summary = result["summary"]
    if summary["created"] + summary["updated"] + summary["unchanged"] > 0:
        device.mark_sync_success()
    return JsonResponse(result)
