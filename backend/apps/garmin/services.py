"""Garmin provider service and sync orchestration."""

from __future__ import annotations

import datetime
import json
import math
import secrets
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast
from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    OperationalError,
    router,
    transaction,
)
from django.db.models import Q
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.plans.locks import lock_plan_aggregate_rows
from apps.plans.models import Day

from .models import (
    GARMIN_PROVIDER,
    GarminActivity,
    GarminConnection,
    GarminOAuthState,
    GarminTokenPair,
    ensure_token_encryption_available,
)

_ACTIVITY_TYPE_CYCLE = "cycle"
_ACTIVITY_TYPE_CYCLING = {
    "cycle",
    "cycling",
    "bicycling",
    "bike",
    "bicycle",
    "biking",
}
_ACTIVITY_CALORIES_MAX = 10_000_000
_ACTIVITY_DISTANCE_MAX = Decimal("99999999.99")
_ACTIVITY_DISTANCE_QUANT = Decimal("0.01")
_ACTIVITY_DURATION_MAX_SECONDS = 24 * 60 * 60

_PENDING_RECONCILIATION_REASON_AMBIGUOUS_DAY = "ambiguous_day"
_PENDING_RECONCILIATION_REASON_MISSING_LOCAL = "missing_local_start"

_ACTIVITY_DISTANCE_MILES_TO_KM = Decimal("1.60934")
_ACTIVITY_DISTANCE_SOURCES = (
    "distanceMeters",
    "distanceKm",
    "distance_km",
    "distance",
)

_ACTIVITY_DEFAULT_LOCAL_TIME_KEYS = (
    "start_time",
    "startTime",
    "startTimeInSeconds",
)
_ACTIVITY_START_LOCAL_KEYS = (
    "startTimeLocal",
    "startLocalTime",
    "localStartTime",
    "start_time_local",
)
_ACTIVITY_START_LOCAL_OFFSET_KEYS = (
    "timezoneOffsetMinutes",
    "offsetMinutes",
    "startTimezoneOffset",
    "start_timezone_offset",
)


def _provider_error_message(operation: str, status_code: int) -> str:
    """Normalize HTTP status-classified remote operation errors."""
    if status_code == 401:
        return f"Garmin {operation} unauthorized"
    return f"Garmin {operation} failed"


@dataclass(frozen=True)
class GarminSyncSummary:
    """Outcome of a Garmin sync run."""

    imported: int
    duplicates: int
    unsupported: int
    invalid: int


@dataclass(frozen=True)
class NormalizedActivity:
    """Normalized provider activity row."""

    provider_activity_id: str
    provider_activity_type: str
    started_at: datetime.datetime
    started_at_local_date: datetime.date | None
    started_at_local_time: datetime.time | None
    provider_timezone_offset_minutes: int
    kcals: int
    duration_seconds: int
    distance: Decimal
    provider_account_id: str


def _required_setting(name: str) -> str:
    value = getattr(settings, name, "")
    if not value:
        raise ValueError(f"GARMIN setting {name} is required")
    return str(value)


def _normalize_https_origin(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("GARMIN setting has an invalid hostname")

    if parsed.port is None:
        return f"{parsed.scheme}://{host}"

    if ":" in host:
        return f"{parsed.scheme}://[{host}]:{parsed.port}"

    return f"{parsed.scheme}://{host}:{parsed.port}"


def _required_origin_list(name: str) -> set[str]:
    raw_origins = getattr(settings, name, None)
    if isinstance(raw_origins, str):
        raw_origins = [
            item.strip() for item in raw_origins.split(",") if item.strip()
        ]
    elif raw_origins is None:
        raw_origins = []

    normalized: set[str] = set()
    for origin in raw_origins or []:
        normalized_origin = str(origin).strip()
        if not normalized_origin:
            continue
        parsed = urlsplit(normalized_origin)
        if parsed.scheme != "https":
            raise ValueError(f"GARMIN setting {name} must be HTTPS")
        if parsed.username or parsed.password:
            raise ValueError(f"GARMIN setting {name} has credentials")
        if parsed.fragment:
            raise ValueError(
                f"GARMIN setting {name} must not include fragments"
            )
        if parsed.path not in ("", "/") or parsed.query:
            raise ValueError(f"GARMIN setting {name} must be a HTTPS origin")
        normalized.add(_normalize_https_origin(normalized_origin))

    if not normalized:
        raise ValueError(f"GARMIN setting {name} must be configured")

    return normalized


def _required_positive_int(
    name: str,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    value = getattr(settings, name, None)
    if value is None or isinstance(value, bool):
        raise ValueError(f"GARMIN setting {name} must be an integer")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GARMIN setting {name} must be an integer") from exc

    if parsed < minimum:
        raise ValueError(f"GARMIN setting {name} must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"GARMIN setting {name} must be <= {maximum}")
    return parsed


def _required_https_url(name: str, origin_setting_name: str) -> str:
    value = _required_setting(name)
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise ValueError(f"GARMIN setting {name} must be HTTPS")
    if parsed.username or parsed.password:
        raise ValueError(f"GARMIN setting {name} has credentials")
    if parsed.fragment:
        raise ValueError(f"GARMIN setting {name} must not include fragments")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"GARMIN setting {name} must include a hostname")

    allowed_origins = _required_origin_list(origin_setting_name)
    normalized = _normalize_https_origin(value)
    if normalized not in allowed_origins:
        raise ValueError(f"GARMIN setting {name} has an unapproved origin")

    return value


def _optional_required_https_url(name: str, origin_setting_name: str) -> str:
    value = getattr(settings, name, "")
    if not value:
        return ""
    return _required_https_url(name, origin_setting_name)


def _provider_config() -> dict[str, Any]:
    """Load and validate Garmin settings when integration is enabled."""
    if not bool(getattr(settings, "GARMIN_ENABLED", False)):
        raise ValueError("Garmin integration is disabled")

    ensure_token_encryption_available()

    return {
        "client_id": _required_setting("GARMIN_CLIENT_ID"),
        "client_secret": _required_setting("GARMIN_CLIENT_SECRET"),
        "authorization_url": _required_https_url(
            "GARMIN_AUTHORIZATION_URL",
            "GARMIN_PROVIDER_ORIGINS",
        ),
        "token_url": _required_https_url(
            "GARMIN_TOKEN_URL",
            "GARMIN_PROVIDER_ORIGINS",
        ),
        "activities_url": _required_https_url(
            "GARMIN_ACTIVITIES_URL",
            "GARMIN_PROVIDER_ORIGINS",
        ),
        "callback_url": _required_https_url(
            "GARMIN_CALLBACK_URL",
            "GARMIN_CALLBACK_ALLOWED_ORIGINS",
        ),
        "scopes": _required_setting("GARMIN_SCOPES"),
        "request_timeout": _required_positive_int(
            "GARMIN_REQUEST_TIMEOUT_SECONDS",
            minimum=1,
            maximum=30,
        ),
        "activities_limit": _required_positive_int(
            "GARMIN_ACTIVITIES_LIMIT",
            minimum=1,
            maximum=1000,
        ),
        "activity_max_pages": _required_positive_int(
            "GARMIN_ACTIVITY_MAX_PAGES",
            minimum=1,
            maximum=400,
        ),
        "activity_batch_size": _required_positive_int(
            "GARMIN_ACTIVITY_SYNC_BATCH_SIZE",
            minimum=1,
            maximum=1000,
        ),
        "state_ttl_seconds": _required_positive_int(
            "GARMIN_STATE_TTL_SECONDS",
            minimum=30,
            maximum=3600,
        ),
        "state_max_in_flight": _required_positive_int(
            "GARMIN_STATE_MAX_IN_FLIGHT",
            minimum=1,
            maximum=100,
        ),
        "token_ttl_seconds": _required_positive_int(
            "GARMIN_TOKEN_MAX_TTL_SECONDS",
            minimum=60,
            maximum=604800,
        ),
        "activity_response_max_bytes": _required_positive_int(
            "GARMIN_ACTIVITY_ENDPOINT_MAX_RESPONSE_BYTES",
            minimum=1024,
            maximum=10 * 1024 * 1024,
        ),
        "token_response_max_bytes": _required_positive_int(
            "GARMIN_TOKEN_ENDPOINT_MAX_RESPONSE_BYTES",
            minimum=1024,
            maximum=10 * 1024 * 1024,
        ),
        "revoke_token_url": _optional_required_https_url(
            "GARMIN_REVOKE_TOKEN_URL",
            "GARMIN_PROVIDER_ORIGINS",
        ),
    }


def _request_json(
    method: str,
    url: str,
    operation: str,
    *,
    timeout: float,
    max_response_bytes: int,
    **kwargs: Any,
) -> dict[str, object]:
    """Perform a one-shot request and validate a dict JSON body."""
    try:
        response = requests.request(
            method,
            url,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise ValueError(f"Garmin {operation} failed") from exc

    with response:
        if response.status_code >= 400:
            raise ValueError(
                _provider_error_message(operation, response.status_code)
            )

        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_response_bytes:
                    raise ValueError(
                        f"Garmin {operation} response exceeded limit"
                    )
            except ValueError as exc:
                raise ValueError(
                    f"Garmin {operation} response invalid content length"
                ) from exc

        chunks: list[bytes] = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=1024):
            if not chunk:
                continue

            total_bytes += len(chunk)
            if total_bytes > max_response_bytes:
                raise ValueError(f"Garmin {operation} response exceeded limit")
            chunks.append(chunk)

        payload_bytes = b"".join(chunks)
        try:
            payload_text = payload_bytes.decode(response.encoding or "utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Garmin {operation} returned invalid JSON"
            ) from exc

        try:
            payload = json.loads(payload_text)
        except ValueError as exc:
            raise ValueError(
                f"Garmin {operation} returned invalid JSON"
            ) from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Garmin {operation} returned invalid JSON")
    return payload


def _coerce_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be non-negative")
    if not isinstance(value, int | float | str):
        raise ValueError(f"{field_name} must be non-negative")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be non-negative") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if isinstance(parsed, float) and not parsed.is_integer():
        raise ValueError(f"{field_name} must be non-negative")
    converted = int(parsed)
    return converted


def _coerce_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be non-negative")
    if not isinstance(value, int | float | str | Decimal):
        raise ValueError(f"{field_name} must be non-negative")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be non-negative") from exc
    if decimal_value.is_nan() or decimal_value.is_infinite():
        raise ValueError(f"{field_name} must be non-negative")
    if decimal_value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return decimal_value


def _normalize_distance_unit(value: object | None) -> str:
    if value is None:
        return "km"

    unit = str(value).strip().lower()
    if unit in {"m", "meter", "meters", "metre", "metres"}:
        return "m"
    if unit in {
        "km",
        "kilometer",
        "kilometers",
        "kms",
        "kilometre",
        "kilometres",
    }:
        return "km"
    raise ValueError("distance unit is unsupported")


def _validate_distance_km(
    raw_distance: object, raw_unit: object, *, source: str
) -> Decimal:
    distance = _coerce_decimal(raw_distance, "distance")

    unit = _normalize_distance_unit(raw_unit)
    if source == "distanceMeters":
        unit = "m"

    if unit == "m":
        distance = distance / Decimal("1000")

    if source == "distanceMiles":
        distance = distance * _ACTIVITY_DISTANCE_MILES_TO_KM

    distance = distance.quantize(
        _ACTIVITY_DISTANCE_QUANT, rounding=ROUND_HALF_UP
    )

    if distance > _ACTIVITY_DISTANCE_MAX:
        raise ValueError("distance out of supported bounds")

    if distance < 0:
        raise ValueError("distance out of supported bounds")

    try:
        Exercise._meta.get_field("distance").clean(distance, None)
    except ValidationError as exc:
        raise ValueError("distance out of supported bounds") from exc
    return distance


def _coerce_started_at(
    value: object,
    *,
    local_value: object | None = None,
    local_offset_minutes: object | None = None,
) -> tuple[datetime.datetime, datetime.date, datetime.time, int]:
    if local_value is None:
        raise ValueError("start time local timezone is required")

    local_dt = _parse_local_start_time(local_value, local_offset_minutes)
    local_tz = local_dt.tzinfo

    if not isinstance(value, datetime.datetime | int | float | str):
        raise ValueError("start time is missing")

    if isinstance(value, int | float):
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError("start time is invalid")
        if seconds > 10**12:
            seconds /= 1000
        _ = datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
    elif isinstance(value, str):
        candidate = value.replace("Z", "+00:00")
        try:
            datetime.datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError("start time is invalid") from exc

    if local_dt is None or local_dt.tzinfo is None:
        raise ValueError("start time must include timezone")

    if local_tz is None:
        raise ValueError("start time must include timezone")

    local_dt = local_dt.astimezone(local_tz)
    offset = local_dt.utcoffset() or datetime.timedelta()
    offset_minutes = int(offset.total_seconds() / 60)
    if abs(offset_minutes) > 14 * 60:
        raise ValueError("start time timezone offset is invalid")

    return (
        local_dt.astimezone(datetime.timezone.utc),
        local_dt.date(),
        local_dt.timetz().replace(tzinfo=None),
        offset_minutes,
    )


def _parse_local_start_time(
    raw_value: object,
    raw_offset_minutes: object | None,
) -> datetime.datetime:
    if not isinstance(raw_value, str):
        raise ValueError("start time is invalid")

    raw = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("start time is invalid") from exc

    if parsed.tzinfo is not None:
        return parsed

    if raw_offset_minutes is None:
        raise ValueError("start time timezone is missing")

    try:
        offset_minutes = int(str(raw_offset_minutes))
    except (TypeError, ValueError) as exc:
        raise ValueError("start time timezone is invalid") from exc

    parsed = parsed.replace(
        tzinfo=datetime.timezone(datetime.timedelta(minutes=offset_minutes)),
    )
    return parsed


def _validate_provider_id(
    field_name: str, value: object, max_length: int
) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long")
    if not text:
        raise ValueError(f"{field_name} is missing")
    return text


def _normalize_payload_id(
    value: object, *, field_name: str, max_length: int
) -> str:
    if value is None:
        raise ValueError(f"{field_name} is missing")
    text = str(value)
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long")
    if not text:
        raise ValueError(f"{field_name} is missing")
    return text


def _extract_payload_distance(
    payload: dict[str, object],
) -> tuple[object, str]:
    if "distanceMeters" in payload and payload["distanceMeters"] is not None:
        return payload["distanceMeters"], "distanceMeters"
    if "distanceMiles" in payload and payload["distanceMiles"] is not None:
        return payload["distanceMiles"], "distanceMiles"
    if "distanceKm" in payload and payload["distanceKm"] is not None:
        return payload["distanceKm"], "distanceKm"
    if "distance_km" in payload and payload["distance_km"] is not None:
        return payload["distance_km"], "distance_km"
    if "distance" in payload and payload["distance"] is not None:
        return payload["distance"], "distance"
    raise ValueError("distance is missing")


def _extract_payload_kcal(payload: dict[str, object]) -> object:
    if payload.get("activeKcal") is not None:
        return payload["activeKcal"]
    if payload.get("activeKilocalories") is not None:
        return payload["activeKilocalories"]
    return payload.get("calories")


def _extract_payload_duration(payload: dict[str, object]) -> object:
    if payload.get("duration") is not None:
        return payload["duration"]
    if payload.get("durationSeconds") is not None:
        return payload["durationSeconds"]
    if payload.get("duration_seconds") is not None:
        return payload["duration_seconds"]
    return 0


def _extract_payload_activity_id(payload: dict[str, object]) -> object:
    return (
        payload.get("activityId")
        if "activityId" in payload
        else payload.get("activity_id")
    )


def _extract_payload_provider_account(payload: dict[str, object]) -> object:
    return payload.get("userId")


def _extract_payload_activity_type(payload: dict[str, object]) -> object:
    return (
        payload.get("activityType")
        if "activityType" in payload
        else payload.get("activity_type")
    )


def _extract_payload_local_start_time(
    payload: dict[str, object],
) -> tuple[object, object | None]:
    for key in _ACTIVITY_START_LOCAL_KEYS:
        if key in payload:
            local_start = payload.get(key)
            if local_start is not None:
                break
    else:
        local_start = None

    offset_value = None
    for key in _ACTIVITY_START_LOCAL_OFFSET_KEYS:
        if key in payload:
            offset_value = payload.get(key)
            if offset_value is not None:
                break
    return local_start, offset_value


def _extract_payload_start(payload: dict[str, object]) -> object | None:
    if "startTime" in payload:
        return payload["startTime"]
    return payload.get("start_time")


def _validate_distance_payload(
    payload: dict[str, object],
) -> Decimal:
    raw_distance, source = _extract_payload_distance(payload)

    raw_unit = payload.get("distanceUnit")
    if source == "distanceMeters":
        raw_unit = "m"

    return _validate_distance_km(raw_distance, raw_unit, source=source)


def _validate_duration(raw_duration: object) -> int:
    duration_seconds = _coerce_non_negative_int(raw_duration, "duration")
    if duration_seconds > _ACTIVITY_DURATION_MAX_SECONDS:
        raise ValueError("duration_seconds out of supported bounds")

    duration = datetime.timedelta(seconds=duration_seconds)
    try:
        Exercise._meta.get_field("duration").clean(duration, None)
    except ValidationError as exc:
        raise ValueError("duration_seconds out of supported bounds") from exc

    return duration_seconds


def _validate_kcals(raw_kcals: object) -> int:
    kcals = _coerce_non_negative_int(raw_kcals, "kcal")
    if kcals > _ACTIVITY_CALORIES_MAX:
        raise ValueError("kcal out of supported bounds")

    try:
        Exercise._meta.get_field("kcals").clean(kcals, None)
    except ValidationError as exc:
        raise ValueError("kcal out of supported bounds") from exc

    return kcals


def _validate_exercise_type(raw_type: object) -> str:
    if not raw_type:
        return _ACTIVITY_TYPE_CYCLE
    activity_type = str(raw_type).strip().lower()
    return (
        _ACTIVITY_TYPE_CYCLE if activity_type in _ACTIVITY_TYPE_CYCLING else ""
    )


def _normalize_activity(payload: object) -> NormalizedActivity:
    if not isinstance(payload, dict):
        raise ValueError("activity payload is invalid")

    activity_id = _normalize_payload_id(
        _extract_payload_activity_id(payload),
        field_name="activityId",
        max_length=255,
    )

    activity_type = _extract_payload_activity_type(payload)
    activity_type = str(activity_type) if activity_type is not None else ""
    activity_type = activity_type.strip().lower()

    local_start_value, local_offset = _extract_payload_local_start_time(
        payload
    )
    started_at = _extract_payload_start(payload)
    start_dt, local_day, local_time, offset_minutes = _coerce_started_at(
        started_at,
        local_value=local_start_value,
        local_offset_minutes=local_offset,
    )

    duration_seconds = _validate_duration(_extract_payload_duration(payload))
    kcals = _validate_kcals(_extract_payload_kcal(payload))
    distance = _validate_distance_payload(payload)

    provider_account_id = str(
        _extract_payload_provider_account(payload) or ""
    ).strip()
    if provider_account_id and len(provider_account_id) > 255:
        raise ValueError("provider_account_id is too long")

    if not activity_type:
        raise ValueError("activityType is missing")

    activity_type = _validate_exercise_type(activity_type)

    return NormalizedActivity(
        provider_activity_id=activity_id,
        provider_activity_type=activity_type,
        started_at=start_dt,
        started_at_local_date=local_day,
        started_at_local_time=local_time,
        provider_timezone_offset_minutes=offset_minutes,
        kcals=kcals,
        duration_seconds=duration_seconds,
        distance=distance,
        provider_account_id=provider_account_id,
    )


def _extract_activity_items(
    payload: dict[str, object],
) -> list[dict[str, object]]:
    raw = payload.get("activities")
    if raw is None:
        raw = payload.get("items")
    if raw is None:
        nested = payload.get("data")
        if isinstance(nested, dict):
            raw = nested.get("activities")
            if raw is None:
                raw = nested.get("items")
            if raw is None and isinstance(payload.get("data"), dict):
                raw = payload.get("data")
        elif isinstance(nested, list):
            raw = nested

    if raw is None and "data" in payload and isinstance(payload["data"], list):
        raw = payload["data"]

    if not isinstance(raw, list):
        raise ValueError("Garmin activities payload is invalid")
    return [item for item in raw if isinstance(item, dict)]


def _extract_next_cursor(payload: dict[str, object]) -> str | None:
    cursor = (
        payload.get("next")
        or payload.get("nextCursor")
        or payload.get("cursor")
    )
    if cursor:
        return str(cursor)

    paging = payload.get("paging")
    if isinstance(paging, dict):
        paging_cursor = paging.get("next") or paging.get("nextCursor")
        if paging_cursor:
            return str(paging_cursor)
    return None


def _iter_activity_payloads(
    access_token: str,
    *,
    max_pages: int,
    page_limit: int,
    timeout: float,
    activities_url: str,
    response_max_bytes: int,
) -> list[dict[str, object]]:
    """Fetch a paginated Garmin activity payload set."""
    payloads: list[dict[str, object]] = []
    seen_cursors: set[str] = set()
    next_cursor: str | None = None

    for page in range(max_pages):
        params: dict[str, str] = {"limit": str(page_limit)}
        if next_cursor is not None:
            params["cursor"] = next_cursor

        payload = _request_json(
            "GET",
            activities_url,
            "activity fetch",
            timeout=timeout,
            max_response_bytes=response_max_bytes,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            params=params,
        )

        payloads.extend(_extract_activity_items(payload))
        next_cursor = _extract_next_cursor(payload)
        if not next_cursor:
            break

        if next_cursor in seen_cursors:
            raise ValueError("Garmin activity pagination loop detected")
        seen_cursors.add(next_cursor)
        if page + 1 == max_pages:
            raise ValueError(
                "Garmin activity pagination exceeded maximum pages"
            )

    return payloads


def _token_request_payload(
    payload: dict[str, str], config: dict[str, Any]
) -> GarminTokenPair:
    response = _request_json(
        "POST",
        config["token_url"],
        "token exchange",
        timeout=float(config["request_timeout"]),
        max_response_bytes=int(config["token_response_max_bytes"]),
        headers={"Accept": "application/json"},
        data=payload,
    )
    return _parse_token_payload(response)


def _parse_token_payload(payload: dict[str, object]) -> GarminTokenPair:
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("Garmin token response has invalid access_token")

    expires_in_raw = payload.get("expires_in")
    if isinstance(expires_in_raw, bool):
        raise ValueError("Garmin token response has invalid expires_in")
    if expires_in_raw is None:
        raise ValueError("Garmin token response has invalid expires_in")
    if not isinstance(expires_in_raw, int | float | str):
        raise ValueError("Garmin token response has invalid expires_in")

    try:
        expires_in_float = float(expires_in_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Garmin token response has invalid expires_in"
        ) from exc

    if not math.isfinite(expires_in_float) or expires_in_float < 0:
        raise ValueError("Garmin token response has invalid expires_in")

    config = _provider_config()
    if int(expires_in_float) > int(config["token_ttl_seconds"]):
        raise ValueError("Garmin token response has invalid expires_in")

    refresh_token = payload.get("refresh_token")
    refresh_token_value = (
        str(refresh_token)
        if isinstance(refresh_token, str) and refresh_token
        else None
    )

    scope = payload.get("scope")
    scope_value = str(scope) if isinstance(scope, str) else None

    provider_account_id = payload.get("userId")
    provider_account_id_value = (
        str(provider_account_id) if provider_account_id is not None else None
    )
    if provider_account_id_value is not None:
        provider_account_id_value = provider_account_id_value[:255]

    return GarminTokenPair(
        access_token=access_token,
        refresh_token=refresh_token_value,
        expires_in=int(expires_in_float),
        scope=scope_value,
        provider_account_id=provider_account_id_value,
    )


def begin_authorization(user) -> tuple[str, datetime.datetime, str]:
    """Generate a short-lived one-time state and authorization URL."""
    config = _provider_config()

    now = timezone.now()
    GarminOAuthState.prune_expired(
        now=now,
        user=user,
        provider=GARMIN_PROVIDER,
    )
    if (
        GarminOAuthState.count_active(
            user=user,
            provider=GARMIN_PROVIDER,
            now=now,
        )
        >= config["state_max_in_flight"]
    ):
        raise ValueError("Too many Garmin OAuth sessions in flight")

    state = secrets.token_urlsafe(24)
    expires_at = now + datetime.timedelta(
        seconds=int(config["state_ttl_seconds"])
    )

    GarminOAuthState.create_for_user(
        user=user,
        raw_state=state,
        provider=GARMIN_PROVIDER,
        expires_at=expires_at,
    )

    authorization_url = f"{config['authorization_url']}?{urlencode({
        'response_type': 'code',
        'client_id': config['client_id'],
        'redirect_uri': config['callback_url'],
        'scope': config['scopes'],
        'state': state,
    })}"

    return authorization_url, expires_at, state


def exchange_code_for_tokens(code: str) -> GarminTokenPair:
    """Exchange authorization code for an OAuth token pair."""
    if not code:
        raise ValueError("Garmin authorization code is required")

    config = _provider_config()
    return _token_request_payload(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config["callback_url"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
        config,
    )


def refresh_access_token(connection: GarminConnection) -> GarminTokenPair:
    """Refresh access token for an existing Garmin connection."""
    if not connection.refresh_token:
        raise ValueError("Garmin refresh token is missing")

    config = _provider_config()
    token = _token_request_payload(
        {
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
        config,
    )

    if token.refresh_token is None:
        return GarminTokenPair(
            access_token=token.access_token,
            refresh_token=connection.refresh_token,
            expires_in=token.expires_in,
            scope=token.scope,
            provider_account_id=token.provider_account_id,
        )
    return token


def revoke_refresh_token(refresh_token: str) -> None:
    """Attempt Garmin token revocation with safe best effort."""
    if not refresh_token:
        return

    config = _provider_config()
    revoke_url = str(config.get("revoke_token_url") or "")
    if not revoke_url:
        return

    try:
        _request_json(
            "POST",
            revoke_url,
            "token revoke",
            timeout=float(config["request_timeout"]),
            max_response_bytes=1024 * 1024,
            headers={"Accept": "application/json"},
            data={
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            },
        )
    except ValueError:
        return


def _refresh_access_token_with_retry(
    connection: GarminConnection,
    using: str,
    *,
    force_refresh: bool = False,
) -> tuple[str, int, str]:
    """Refresh with minimal lock scope and optimistic concurrency control."""
    for attempt in range(2):
        with transaction.atomic(using=using):
            current = (
                GarminConnection.objects.using(using)
                .select_for_update(of=("self",))
                .get(pk=connection.pk)
            )
            if not current.is_active:
                raise ValueError("Garmin connection is not active")

            generation = current.connection_generation
            account_id_snapshot = current.provider_account_id

            if current.has_unexpired_access_token and not force_refresh:
                token = current.access_token
                if token:
                    return token, generation, account_id_snapshot

            refresh_token = current.refresh_token
            if not refresh_token:
                raise ValueError("Garmin refresh token is missing")

        token_pair = refresh_access_token(current)

        with transaction.atomic(using=using):
            current = (
                GarminConnection.objects.using(using)
                .select_for_update(of=("self",))
                .get(pk=connection.pk)
            )
            if not current.is_active:
                raise ValueError("Garmin connection is not active")
            if (
                current.connection_generation != generation
                or current.provider_account_id != account_id_snapshot
            ):
                # Retry to avoid clobbering a concurrent state transition.
                continue

            # Preserve explicitly missing fields from the token response.
            merged_scope = token_pair.scope
            if merged_scope is not None:
                current.provider_scopes = (
                    merged_scope.split() if merged_scope.strip() else []
                )

            current.set_tokens(
                GarminTokenPair(
                    access_token=token_pair.access_token,
                    refresh_token=current.refresh_token
                    or token_pair.refresh_token,
                    expires_in=token_pair.expires_in,
                    provider_account_id=(
                        token_pair.provider_account_id
                        if token_pair.provider_account_id is not None
                        else current.provider_account_id
                    ),
                    scope=(
                        " ".join(current.provider_scopes)
                        if current.provider_scopes
                        else (token_pair.scope or None)
                    ),
                ),
                expires_in=token_pair.expires_in,
            )
            current.save(
                using=using,
                update_fields=[
                    "access_token_encrypted",
                    "refresh_token_encrypted",
                    "access_token_expires_at",
                    "provider_scopes",
                    "provider_account_id",
                    "connection_generation",
                    "status",
                    "updated_at",
                ],
            )
            current.refresh_from_db(
                fields=[
                    "connection_generation",
                    "provider_account_id",
                    "access_token_expires_at",
                ]
            )
            if not current.access_token:
                raise ValueError("Garmin access token is unavailable")
            token_account_id = (
                token_pair.provider_account_id
                if token_pair.provider_account_id is not None
                else account_id_snapshot
            )
            return (
                current.access_token,
                current.connection_generation,
                token_account_id,
            )

    raise ValueError("Garmin access token refresh failed")


def _ensure_access_token(
    connection: GarminConnection, *, force_refresh: bool = False
) -> tuple[str, int, str]:
    if not connection.can_sync:
        raise ValueError("Garmin connection is not connected")

    if connection.has_unexpired_access_token:
        if force_refresh:
            using = router.db_for_write(type(connection), instance=connection)
            return _refresh_access_token_with_retry(
                connection,
                using,
                force_refresh=True,
            )
        access_token = connection.access_token
        if access_token:
            return (
                access_token,
                connection.connection_generation,
                connection.provider_account_id,
            )

    using = router.db_for_write(type(connection), instance=connection)
    return _refresh_access_token_with_retry(connection, using)


def _resolve_day_for_activity(
    connection: GarminConnection,
    started_at_local_date: datetime.date | None,
    *,
    using: str,
) -> Day | None:
    if started_at_local_date is None:
        return None

    queryset = Day.objects.using(using).filter(
        day=started_at_local_date,
        plan__user=connection.user,
    )
    count = queryset.count()
    if count == 0:
        return None
    if count > 1:
        raise ValueError("Garmin activity day is ambiguous")
    return queryset.select_related("plan").first()


def _ensure_exercise(
    garmin_activity: GarminActivity,
    *,
    day: Day,
    activity: NormalizedActivity,
    using: str,
) -> None:
    if garmin_activity.exercise_id is None:
        exercise = Exercise.objects.using(using).create(
            day=day,
            time=activity.started_at_local_time or datetime.time(0, 0),
            type=Exercise.EXERCISE_CYCLE,
            kcals=activity.kcals,
            duration=datetime.timedelta(seconds=activity.duration_seconds),
            distance=activity.distance,
        )
        garmin_activity.exercise = exercise
        garmin_activity.save(
            using=using,
            update_fields=["exercise"],
        )
        return
    try:
        exercise = cast(
            Exercise,
            Exercise.objects.using(using)
            .select_for_update(of=("self",))
            .get(pk=garmin_activity.exercise_id),
        )
    except Exercise.DoesNotExist:
        exercise = Exercise.objects.using(using).create(
            day=day,
            time=activity.started_at_local_time or datetime.time(0, 0),
            type=Exercise.EXERCISE_CYCLE,
            kcals=activity.kcals,
            duration=datetime.timedelta(seconds=activity.duration_seconds),
            distance=activity.distance,
        )
        garmin_activity.exercise = exercise
        garmin_activity.save(
            using=using,
            update_fields=["exercise"],
        )
        return

    updated: list[str] = []
    exercise_fields = {
        "day": day,
        "time": activity.started_at_local_time or exercise.time,
        "kcals": activity.kcals,
        "duration": datetime.timedelta(seconds=activity.duration_seconds),
        "distance": activity.distance,
    }

    for field, value in exercise_fields.items():
        if getattr(exercise, field) == value:
            continue
        setattr(exercise, field, value)
        updated.append(field)

    if exercise.type != Exercise.EXERCISE_CYCLE:
        exercise.type = Exercise.EXERCISE_CYCLE
        updated.append("type")

    if updated:
        exercise.save(using=using, update_fields=updated)


def _determine_pending_reason(
    day: Day | None,
    activity: NormalizedActivity,
    resolve_error: str,
) -> str:
    if resolve_error:
        return resolve_error
    if day is None:
        if activity.started_at_local_date is None:
            return _PENDING_RECONCILIATION_REASON_MISSING_LOCAL
        return "day_not_found"
    return ""


def _recompute_days_from_locked_rows(
    locked_days: dict[int, Day],
    day_ids: set[int],
    *,
    using: str,
) -> None:
    for day_id in sorted(day_ids):
        if day_id in locked_days:
            locked_days[day_id].save(using=using)


def sync_connection(connection: GarminConnection) -> GarminSyncSummary:
    """Import Garmin activities for a connection and return a summary."""
    if not isinstance(connection, GarminConnection):
        raise TypeError("connection must be GarminConnection")

    if not connection.user_id:
        raise ValueError("Garmin connection is missing user")

    using = router.db_for_write(type(connection), instance=connection)
    config = _provider_config()

    (
        access_token,
        expected_generation,
        expected_provider_account_id,
    ) = _ensure_access_token(connection)

    for attempt in range(2):
        try:
            raw_activities = _iter_activity_payloads(
                access_token,
                max_pages=int(config["activity_max_pages"]),
                page_limit=int(config["activities_limit"]),
                timeout=float(config["request_timeout"]),
                activities_url=str(config["activities_url"]),
                response_max_bytes=int(config["activity_response_max_bytes"]),
            )
            break
        except ValueError as exc:
            if attempt == 0 and "Garmin activity fetch unauthorized" in str(
                exc
            ):
                (
                    access_token,
                    expected_generation,
                    expected_provider_account_id,
                ) = _ensure_access_token(connection, force_refresh=True)
                continue
            raise
    else:
        raise ValueError("Garmin activity fetch failed")

    imported = 0
    duplicates = 0
    unsupported = 0
    invalid = 0

    candidate_activities: dict[
        tuple[str, str], tuple[NormalizedActivity, Day | None, str]
    ] = {}

    for raw_activity in raw_activities:
        try:
            normalized = _normalize_activity(raw_activity)
        except ValueError:
            invalid += 1
            continue

        if normalized.provider_activity_type != _ACTIVITY_TYPE_CYCLE:
            unsupported += 1
            continue

        if connection.provider_account_id and normalized.provider_account_id:
            if (
                normalized.provider_account_id
                != connection.provider_account_id
            ):
                invalid += 1
                continue

        provider_account_id = (
            normalized.provider_account_id or connection.provider_account_id
        )

        resolve_error = ""
        try:
            day = _resolve_day_for_activity(
                connection,
                normalized.started_at_local_date,
                using=using,
            )
        except ValueError:
            day = None
            resolve_error = _PENDING_RECONCILIATION_REASON_AMBIGUOUS_DAY

        key = (provider_account_id, normalized.provider_activity_id)
        candidate_activities.setdefault(
            key,
            (normalized, day, resolve_error),
        )

    candidates = sorted(
        candidate_activities.items(),
        key=lambda item: item[0],
    )
    batch_size = int(config["activity_batch_size"])
    connection_model_pk = connection.pk

    if batch_size <= 0:
        batch_size = 1

    try:
        for batch_offset in range(0, len(candidates), batch_size):
            batch = candidates[slice(batch_offset, batch_offset + batch_size)]
            batch_filters = Q()
            for provider_account_id, provider_activity_id in (
                key for key, _ in batch
            ):
                batch_filters |= Q(
                    provider_account_id=provider_account_id,
                    provider_activity_id=provider_activity_id,
                )

            with transaction.atomic(using=using):
                connection = (
                    GarminConnection.objects.using(using)
                    .select_for_update(of=("self",))
                    .get(pk=connection_model_pk)
                )
                if not connection.is_active:
                    raise ValueError("Garmin connection is not active")
                if (
                    connection.connection_generation != expected_generation
                    or connection.provider_account_id
                    != expected_provider_account_id
                ):
                    raise ValueError(
                        "Garmin connection state changed during sync"
                    )

                resolved_existing = {
                    (
                        row.provider_account_id,
                        row.provider_activity_id,
                    ): row
                    for row in GarminActivity.objects.using(using)
                    .filter(
                        connection=connection,
                    )
                    .filter(batch_filters)
                    .select_related("exercise")
                }

                day_ids: set[int] = {
                    row.day_id
                    for row in resolved_existing.values()
                    if row.day_id is not None
                }

                for row in resolved_existing.values():
                    exercise = row.exercise
                    if exercise is not None:
                        day_ids.add(exercise.day_id)

                for _, (_, resolved_day, _) in batch:
                    if resolved_day is not None:
                        day_ids.add(resolved_day.pk)

                locks = None
                if day_ids:
                    locks = lock_plan_aggregate_rows(
                        using=using,
                        day_ids=tuple(sorted(day_ids)),
                    )

                locked_days = locks.days_by_pk if locks is not None else {}
                try:
                    for key, (
                        normalized,
                        resolved_day,
                        resolve_error,
                    ) in batch:
                        provider_account_id = key[0]
                        if resolved_day is not None:
                            normalized_day = locked_days.get(
                                resolved_day.pk,
                                resolved_day,
                            )
                        else:
                            normalized_day = None

                        pending_reason = _determine_pending_reason(
                            normalized_day,
                            normalized,
                            resolve_error,
                        )

                        existing = resolved_existing.get(key)
                        if existing is None:
                            provider_timezone_offset_minutes = (
                                normalized.provider_timezone_offset_minutes
                            )
                            pending_reconciliation = bool(pending_reason)
                            garmin_activity = (
                                GarminActivity.objects.db_manager(
                                    using
                                ).create(
                                    connection=connection,
                                    provider_activity_id=(
                                        normalized.provider_activity_id
                                    ),
                                    provider_activity_type=(
                                        normalized.provider_activity_type
                                    ),
                                    provider_account_id=provider_account_id,
                                    day=normalized_day,
                                    provider_local_started_date=(
                                        normalized.started_at_local_date
                                    ),
                                    provider_local_started_time=(
                                        normalized.started_at_local_time
                                    ),
                                    provider_timezone_offset_minutes=(
                                        provider_timezone_offset_minutes
                                    ),
                                    started_at=normalized.started_at,
                                    kcals=normalized.kcals,
                                    duration_seconds=(
                                        normalized.duration_seconds
                                    ),
                                    distance=normalized.distance,
                                    pending_reconciliation=(
                                        pending_reconciliation
                                    ),
                                    pending_reconciliation_reason=(
                                        pending_reason
                                    ),
                                )
                            )
                            imported += 1

                            if normalized_day is not None:
                                _ensure_exercise(
                                    garmin_activity,
                                    day=normalized_day,
                                    activity=normalized,
                                    using=using,
                                )
                            continue

                        garmin_activity = (
                            GarminActivity.objects.using(using)
                            .select_for_update(of=("self",))
                            .get(pk=existing.pk)
                        )
                        previous_day_id = garmin_activity.day_id
                        previous_exercise_day_id = None
                        if garmin_activity.exercise_id is not None:
                            previous_exercise_day_id = (
                                Exercise.objects.using(using)
                                .filter(pk=garmin_activity.exercise_id)
                                .values_list("day_id", flat=True)
                                .first()
                            )

                        garmin_activity.provider_activity_type = (
                            normalized.provider_activity_type
                        )
                        garmin_activity.provider_account_id = (
                            provider_account_id
                        )
                        garmin_activity.day = (
                            normalized_day if not pending_reason else None
                        )
                        if pending_reason:
                            garmin_activity.exercise = None
                        garmin_activity.provider_local_started_date = (
                            normalized.started_at_local_date
                        )
                        garmin_activity.provider_local_started_time = (
                            normalized.started_at_local_time
                        )
                        garmin_activity.provider_timezone_offset_minutes = (
                            normalized.provider_timezone_offset_minutes
                        )
                        garmin_activity.started_at = normalized.started_at
                        garmin_activity.kcals = normalized.kcals
                        garmin_activity.duration_seconds = (
                            normalized.duration_seconds
                        )
                        garmin_activity.distance = normalized.distance
                        garmin_activity.pending_reconciliation = bool(
                            pending_reason
                        )
                        garmin_activity.pending_reconciliation_reason = (
                            pending_reason
                        )
                        garmin_activity.save(
                            using=using,
                            update_fields=[
                                "provider_activity_type",
                                "provider_account_id",
                                "day",
                                "exercise",
                                "provider_local_started_date",
                                "provider_local_started_time",
                                "provider_timezone_offset_minutes",
                                "started_at",
                                "kcals",
                                "duration_seconds",
                                "distance",
                                "pending_reconciliation",
                                "pending_reconciliation_reason",
                            ],
                        )
                        duplicates += 1

                        if pending_reason:
                            continue
                        if (
                            normalized_day is None
                            or garmin_activity.day_id is None
                        ):
                            raise ValueError(
                                "Garmin activity day resolution is inconsistent"
                            )

                        _ensure_exercise(
                            garmin_activity,
                            day=normalized_day,
                            activity=normalized,
                            using=using,
                        )

                        locked_day_ids: set[int] = {garmin_activity.day_id}
                        if previous_day_id is not None:
                            locked_day_ids.add(previous_day_id)
                        if previous_exercise_day_id is not None:
                            locked_day_ids.add(previous_exercise_day_id)
                        _recompute_days_from_locked_rows(
                            locked_days,
                            locked_day_ids,
                            using=using,
                        )
                finally:
                    if locks is not None:
                        locks.clear_markers()

        with transaction.atomic(using=using):
            connection = (
                GarminConnection.objects.using(using)
                .select_for_update(of=("self",))
                .get(pk=connection_model_pk)
            )
            if not connection.is_active:
                raise ValueError("Garmin connection is not active")
            if (
                connection.connection_generation != expected_generation
                or connection.provider_account_id
                != expected_provider_account_id
            ):
                raise ValueError("Garmin connection state changed during sync")

            connection.last_synced_at = timezone.now()
            connection.last_sync_summary = {
                "imported": imported,
                "duplicates": duplicates,
                "unsupported": unsupported,
                "invalid": invalid,
            }
            connection.save(
                using=using,
                update_fields=[
                    "last_synced_at",
                    "last_sync_summary",
                    "access_token_expires_at",
                    "updated_at",
                ],
            )
    except (IntegrityError, OperationalError) as exc:
        raise ValueError("Garmin activity import failed") from exc

    return GarminSyncSummary(
        imported=imported,
        duplicates=duplicates,
        unsupported=unsupported,
        invalid=invalid,
    )


def reconcile_pending_garmin_activities(connection: GarminConnection) -> int:
    """Attempt to reconcile unmatched valid provenance activities."""
    using = router.db_for_write(type(connection), instance=connection)

    reconciled = 0
    with transaction.atomic(using=using):
        connection = (
            GarminConnection.objects.using(using)
            .select_for_update(of=("self",))
            .get(pk=connection.pk)
        )
        if not connection.is_active:
            raise ValueError("Garmin connection is not active")

        expected_generation = connection.connection_generation
        expected_provider_account_id = connection.provider_account_id

        pending_ids = list(
            GarminActivity.objects.using(using)
            .filter(
                connection=connection,
                pending_reconciliation=True,
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )

        for activity_id in pending_ids:
            try:
                activity = (
                    GarminActivity.objects.using(using)
                    .select_for_update(of=("self",))
                    .get(pk=activity_id)
                )
            except GarminActivity.DoesNotExist:
                continue
            if not activity.pending_reconciliation:
                continue

            if (
                connection.connection_generation != expected_generation
                or connection.provider_account_id
                != expected_provider_account_id
            ):
                raise ValueError("Garmin connection state changed during sync")

            resolve_error = ""
            try:
                day = _resolve_day_for_activity(
                    connection,
                    activity.provider_local_started_date,
                    using=using,
                )
            except ValueError:
                day = None
                resolve_error = _PENDING_RECONCILIATION_REASON_AMBIGUOUS_DAY

            pending_reason = _determine_pending_reason(
                day,
                NormalizedActivity(
                    provider_activity_id=activity.provider_activity_id,
                    provider_activity_type=activity.provider_activity_type,
                    started_at=activity.started_at,
                    started_at_local_date=activity.provider_local_started_date,
                    started_at_local_time=activity.provider_local_started_time,
                    provider_timezone_offset_minutes=(
                        activity.provider_timezone_offset_minutes
                    ),
                    kcals=activity.kcals,
                    duration_seconds=activity.duration_seconds,
                    distance=activity.distance,
                    provider_account_id=activity.provider_account_id,
                ),
                resolve_error,
            )
            previous_day_id = activity.day_id
            locked_rows = None
            if day is not None:
                locked_rows = lock_plan_aggregate_rows(
                    using=using,
                    day_ids=tuple(
                        d for d in {previous_day_id, day.pk} if d is not None
                    ),
                )
                day = locked_rows.days_by_pk[day.pk]
                activity.day = day
            else:
                day = None
                activity.day = None
                activity.exercise = None

            activity.pending_reconciliation = bool(pending_reason)
            activity.pending_reconciliation_reason = pending_reason
            update_fields = [
                "day",
                "exercise",
                "pending_reconciliation",
                "pending_reconciliation_reason",
            ]
            activity.save(using=using, update_fields=update_fields)

            if not pending_reason:
                assert day is not None
                _ensure_exercise(
                    activity,
                    day=day,
                    activity=NormalizedActivity(
                        provider_activity_id=activity.provider_activity_id,
                        provider_activity_type=activity.provider_activity_type,
                        started_at=activity.started_at,
                        started_at_local_date=(
                            activity.provider_local_started_date
                        ),
                        started_at_local_time=(
                            activity.provider_local_started_time
                        ),
                        provider_timezone_offset_minutes=(
                            activity.provider_timezone_offset_minutes
                        ),
                        kcals=activity.kcals,
                        duration_seconds=activity.duration_seconds,
                        distance=activity.distance,
                        provider_account_id=activity.provider_account_id,
                    ),
                    using=using,
                )
                if locked_rows is not None:
                    _recompute_days_from_locked_rows(
                        locked_rows.days_by_pk,
                        (
                            {day.pk, previous_day_id}
                            if previous_day_id is not None
                            else {day.pk}
                        ),
                        using=using,
                    )

            reconciled += 1

    return reconciled


def sync_all_connections() -> dict[int, GarminSyncSummary]:
    """Sync every currently connected Garmin connection."""
    if not bool(getattr(settings, "GARMIN_ENABLED", False)):
        return {}

    query = GarminConnection.objects.filter(
        Q(status=GarminConnection.Status.ACTIVE)
        & (
            Q(access_token_encrypted__gt="")
            | Q(refresh_token_encrypted__gt="")
        )
    )

    results: dict[int, GarminSyncSummary] = {}
    for connection in query.order_by("pk"):
        try:
            results[connection.pk] = sync_connection(connection)
        except ValueError:
            continue
    return results
