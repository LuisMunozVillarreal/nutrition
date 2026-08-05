"""Garmin provider service and sync orchestration."""

from __future__ import annotations

import datetime
import json
import math
import secrets
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterator, cast
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
from apps.plans.locks import (
    lock_plan_aggregate_rows,
    lock_user_for_garmin_sync,
)
from apps.plans.models import Day

from .models import (
    GARMIN_PROVIDER,
    GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT,
    GarminActivity,
    GarminConnection,
    GarminOAuthState,
    GarminTokenPair,
    ensure_token_encryption_available,
    is_provider_account_ownership_conflict,
)

_ACTIVITY_TYPE_CYCLE = "cycle"
_EMPTY_CIPHERTEXT = str()
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
_DATETIME_MIN_TIMESTAMP_SECONDS = -62_135_596_800
_DATETIME_MAX_TIMESTAMP_SECONDS = 253_402_300_799
_TIMEZONE_OFFSET_MAX_MINUTES = 14 * 60

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
        "activity_max_total_items": _required_positive_int(
            "GARMIN_ACTIVITY_MAX_TOTAL_ITEMS",
            minimum=1,
            maximum=50_000,
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
        "activity_total_response_max_bytes": _required_positive_int(
            "GARMIN_ACTIVITY_ENDPOINT_MAX_TOTAL_BYTES",
            minimum=1024,
            maximum=50 * 1024 * 1024,
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
        if response.status_code < 200 or response.status_code >= 300:
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
        try:
            for chunk in response.iter_content(chunk_size=1024):
                if not chunk:
                    continue

                total_bytes += len(chunk)
                if total_bytes > max_response_bytes:
                    raise ValueError(
                        f"Garmin {operation} response exceeded limit"
                    )
                chunks.append(chunk)
        except requests.RequestException as exc:
            raise ValueError(f"Garmin {operation} failed") from exc

        payload_bytes = b"".join(chunks)
        try:
            payload_text = payload_bytes.decode(response.encoding or "utf-8")
        except (LookupError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"Garmin {operation} returned invalid JSON"
            ) from exc

        try:
            payload = json.loads(payload_text)
        except (RecursionError, ValueError) as exc:
            raise ValueError(
                f"Garmin {operation} returned invalid JSON"
            ) from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Garmin {operation} returned invalid JSON")
    return payload


def _request_json_with_size(
    method: str,
    url: str,
    operation: str,
    *,
    timeout: float,
    max_response_bytes: int,
    **kwargs: Any,
) -> tuple[dict[str, object], int]:
    """Like ``_request_json`` but also return the consumed body byte count."""
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
        if response.status_code < 200 or response.status_code >= 300:
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
        try:
            for chunk in response.iter_content(chunk_size=1024):
                if not chunk:
                    continue

                total_bytes += len(chunk)
                if total_bytes > max_response_bytes:
                    raise ValueError(
                        f"Garmin {operation} response exceeded limit"
                    )
                chunks.append(chunk)
        except requests.RequestException as exc:
            raise ValueError(f"Garmin {operation} failed") from exc

        payload_bytes = b"".join(chunks)
        try:
            payload_text = payload_bytes.decode(response.encoding or "utf-8")
        except (LookupError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"Garmin {operation} returned invalid JSON"
            ) from exc

        try:
            payload = json.loads(payload_text)
        except (RecursionError, ValueError) as exc:
            raise ValueError(
                f"Garmin {operation} returned invalid JSON"
            ) from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Garmin {operation} returned invalid JSON")
    return payload, total_bytes


def _coerce_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be non-negative")
    if not isinstance(value, int | float | str):
        raise ValueError(f"{field_name} must be non-negative")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
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
    if unit in {"mi", "mile", "miles"}:
        return "mile"
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

    if source == "distanceMiles":
        unit = _normalize_distance_unit(raw_unit or "mile")
        if unit != "mile":
            raise ValueError("distance unit is unsupported")
    else:
        unit = _normalize_distance_unit(raw_unit)

    if source == "distanceMeters":
        unit = "m"

    maximum_source_distance = _ACTIVITY_DISTANCE_MAX
    if unit == "m":
        maximum_source_distance *= Decimal("1000")
    elif unit == "mile":
        maximum_source_distance /= _ACTIVITY_DISTANCE_MILES_TO_KM

    if distance > maximum_source_distance:
        raise ValueError("distance out of supported bounds")

    if unit == "m":
        distance = distance / Decimal("1000")
    elif unit == "mile":
        distance = distance * _ACTIVITY_DISTANCE_MILES_TO_KM

    try:
        distance = distance.quantize(
            _ACTIVITY_DISTANCE_QUANT, rounding=ROUND_HALF_UP
        )
    except InvalidOperation as exc:
        raise ValueError("distance out of supported bounds") from exc

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
    if local_tz is None:
        raise ValueError("start time must include timezone")

    local_dt = local_dt.astimezone(local_tz)
    offset = local_dt.utcoffset()
    if offset is None:
        raise ValueError("start time must include timezone")
    offset_minutes = int(offset.total_seconds() / 60)
    if offset.total_seconds() % 60 != 0:
        raise ValueError("start time timezone offset is invalid")
    if abs(offset_minutes) > _TIMEZONE_OFFSET_MAX_MINUTES:
        raise ValueError("start time timezone offset is invalid")

    try:
        local_utc = local_dt.astimezone(datetime.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("start time is invalid") from exc

    canonical_dt = _parse_canonical_start_time(
        value,
        matching_utc=local_utc,
    )
    try:
        canonical_utc = canonical_dt.astimezone(datetime.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("start time is invalid") from exc
    # Both accepted provider forms preserve microseconds, so accepting a
    # tolerance would hide a genuine date, time, or offset contradiction.
    if canonical_utc != local_utc:
        raise ValueError("start time is inconsistent")

    return (
        canonical_utc,
        local_dt.date(),
        local_dt.timetz().replace(tzinfo=None),
        offset_minutes,
    )


def _parse_canonical_start_time(
    value: object,
    *,
    matching_utc: datetime.datetime,
) -> datetime.datetime:
    if isinstance(value, bool) or not isinstance(
        value, datetime.datetime | int | float | str
    ):
        raise ValueError("start time is missing")

    if isinstance(value, datetime.datetime):
        parsed = value
    elif isinstance(value, int | float):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("start time is invalid") from exc
        if not math.isfinite(numeric_value):
            raise ValueError("start time is invalid")

        candidates: list[datetime.datetime] = []
        for divisor in (1, 1000):
            seconds = numeric_value / divisor
            if not (
                _DATETIME_MIN_TIMESTAMP_SECONDS
                <= seconds
                <= _DATETIME_MAX_TIMESTAMP_SECONDS
            ):
                continue
            try:
                candidates.append(
                    datetime.datetime.fromtimestamp(
                        seconds,
                        tz=datetime.timezone.utc,
                    )
                )
            except (OverflowError, OSError, ValueError):
                continue
        if not candidates:
            raise ValueError("start time is invalid")

        matches = [
            candidate for candidate in candidates if candidate == matching_utc
        ]
        if len(matches) != 1:
            raise ValueError("start time is inconsistent")
        parsed = matches[0]
    else:
        candidate = value.replace("Z", "+00:00")
        try:
            parsed = datetime.datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError("start time is invalid") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("start time must include timezone")
    return parsed


def _parse_timezone_offset_minutes(raw_value: object) -> int:
    try:
        offset_minutes = int(str(raw_value))
    except (TypeError, ValueError) as exc:
        raise ValueError("start time timezone is invalid") from exc
    if abs(offset_minutes) > _TIMEZONE_OFFSET_MAX_MINUTES:
        raise ValueError("start time timezone is invalid")
    return offset_minutes


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
        if raw_offset_minutes is not None:
            offset_minutes = _parse_timezone_offset_minutes(raw_offset_minutes)
            if parsed.utcoffset() != datetime.timedelta(
                minutes=offset_minutes
            ):
                raise ValueError("start time is inconsistent")
        return parsed

    if raw_offset_minutes is None:
        raise ValueError("start time timezone is missing")

    offset_minutes = _parse_timezone_offset_minutes(raw_offset_minutes)
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


def _normalize_optional_payload_id(
    value: object, *, field_name: str, max_length: int
) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long")
    return text or None


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
    raise ValueError("duration is missing")


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

    provider_account_id = _normalize_optional_payload_id(
        _extract_payload_provider_account(payload),
        field_name="provider_account_id",
        max_length=255,
    )
    if provider_account_id is None:
        provider_account_id = ""

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
) -> list[object]:
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
    return raw


def _is_garmin_derived_exercise(
    *,
    exercise: Exercise,
    activity: NormalizedActivity,
    linked_day_id: int | None,
) -> bool:
    """Return whether an exercise still matches its persisted import provenance."""
    expected_time = (
        activity.started_at_local_time
        if activity.started_at_local_time is not None
        else datetime.time(0, 0)
    )
    expected_duration = datetime.timedelta(seconds=activity.duration_seconds)
    return (
        exercise.type == Exercise.EXERCISE_CYCLE
        and exercise.day_id == linked_day_id
        and exercise.time == expected_time
        and exercise.kcals == activity.kcals
        and exercise.duration == expected_duration
        and exercise.distance == activity.distance
    )


def _retire_garmin_derived_exercise(
    *,
    garmin_activity: GarminActivity,
    activity: NormalizedActivity,
    linked_day_id: int | None,
    using: str,
) -> int | None:
    """Delete a derived Garmin exercise and return the previously linked day id."""
    if garmin_activity.exercise_id is None:
        return None

    exercise = (
        Exercise.objects.using(using)
        .select_related("day")
        .select_for_update(of=("self",))
        .filter(pk=garmin_activity.exercise_id)
        .first()
    )
    if exercise is None:
        return None
    if exercise.day is None:
        return None
    if exercise.day.plan_id is None or exercise.day.plan.user_id != (
        garmin_activity.connection.user_id
    ):
        return None

    if exercise.day_id is None or not _is_garmin_derived_exercise(
        exercise=exercise,
        activity=activity,
        linked_day_id=linked_day_id,
    ):
        return None

    day_id = exercise.day_id
    exercise.delete(using=using)
    return day_id


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
    activity_max_total_items: int | None = None,
    activity_total_response_max_bytes: int | None = None,
) -> Iterator[object]:
    """Fetch a paginated Garmin activity payload set."""
    if activity_max_total_items is None:
        activity_max_total_items = int(
            _provider_config()["activity_max_total_items"]
        )
    if activity_total_response_max_bytes is None:
        activity_total_response_max_bytes = int(
            _provider_config()["activity_total_response_max_bytes"]
        )

    total_items = 0
    total_response_bytes = 0
    seen_cursors: set[str] = set()
    next_cursor: str | None = None

    for page in range(max_pages):
        params: dict[str, str] = {"limit": str(page_limit)}
        if next_cursor is not None:
            params["cursor"] = next_cursor

        payload, response_bytes = _request_json_with_size(
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
        total_response_bytes += response_bytes
        if total_response_bytes > activity_total_response_max_bytes:
            raise ValueError(
                "Garmin activity responses exceeded total byte limit"
            )

        for payload_item in _extract_activity_items(payload):
            total_items += 1
            if total_items > activity_max_total_items:
                raise ValueError(
                    "Garmin activity payloads exceeded total item limit"
                )
            yield payload_item

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


def _token_request_payload(
    payload: dict[str, str],
    config: dict[str, Any],
    *,
    require_refresh_token: bool = False,
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
    return _parse_token_payload(
        response,
        require_refresh_token=require_refresh_token,
    )


def _parse_token_payload(
    payload: dict[str, object],
    *,
    require_refresh_token: bool = False,
) -> GarminTokenPair:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "Garmin token response has invalid expires_in"
        ) from exc

    if not math.isfinite(expires_in_float) or expires_in_float < 0:
        raise ValueError("Garmin token response has invalid expires_in")

    try:
        max_ttl = int(getattr(settings, "GARMIN_TOKEN_MAX_TTL_SECONDS", 0))
    except (TypeError, ValueError):
        max_ttl = 0

    if max_ttl > 0 and int(expires_in_float) > max_ttl:
        raise ValueError("Garmin token response has invalid expires_in")

    refresh_token_value = None
    if "refresh_token" in payload:
        refresh_token = payload["refresh_token"]
        if not isinstance(refresh_token, str) or not refresh_token:
            raise ValueError("Garmin token response has invalid refresh_token")
        refresh_token_value = refresh_token
    elif require_refresh_token:
        raise ValueError("Garmin token response has invalid refresh_token")

    scope = payload.get("scope")
    scope_value = str(scope) if isinstance(scope, str) else None

    provider_account_id = payload.get("userId")
    provider_account_id_value = _normalize_optional_payload_id(
        provider_account_id,
        field_name="provider_account_id",
        max_length=255,
    )

    return GarminTokenPair(
        access_token=access_token,
        refresh_token=refresh_token_value,
        expires_in=int(expires_in_float),
        scope=scope_value,
        provider_account_id=provider_account_id_value,
    )


def begin_authorization(user: Any) -> tuple[str, datetime.datetime, str]:
    """Generate a short-lived one-time state and authorization URL."""
    config = _provider_config()

    using = router.db_for_write(GarminOAuthState, instance=user)
    now = timezone.now()
    with transaction.atomic(using=using):
        type(user).objects.using(using).select_for_update(of=("self",)).get(
            pk=user.pk
        )
        GarminOAuthState.prune_expired(
            now=now,
            user=user,
            provider=GARMIN_PROVIDER,
            retention_seconds=config["state_ttl_seconds"],
            using=using,
        )
        if (
            GarminOAuthState.count_active(
                user=user,
                provider=GARMIN_PROVIDER,
                now=now,
                using=using,
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
            using=using,
        )
    authorization_query = urlencode(
        {
            "response_type": "code",
            "client_id": config["client_id"],
            "redirect_uri": config["callback_url"],
            "scope": config["scopes"],
            "state": state,
        }
    )
    authorization_url = f"{config['authorization_url']}?{authorization_query}"

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
        require_refresh_token=True,
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
            if (
                account_id_snapshot
                and token_pair.provider_account_id
                and token_pair.provider_account_id != account_id_snapshot
            ):
                raise ValueError(
                    "Garmin provider account changed during refresh"
                )
            if (
                token_pair.provider_account_id
                and token_pair.provider_account_id
                != current.provider_account_id
            ):
                _reject_external_account_claim(
                    provider=current.provider,
                    provider_account_id=token_pair.provider_account_id,
                    exclude_pk=current.pk,
                    using=using,
                )

            # Preserve explicitly missing fields from the token response.
            merged_scope = token_pair.scope
            if merged_scope is not None:
                current.provider_scopes = (
                    merged_scope.split() if merged_scope.strip() else []
                )

            current.set_tokens(
                GarminTokenPair(
                    access_token=token_pair.access_token,
                    refresh_token=(
                        token_pair.refresh_token
                        if token_pair.refresh_token is not None
                        else current.refresh_token
                    ),
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
            try:
                with transaction.atomic(using=using):
                    current.save(
                        using=using,
                        update_fields=[
                            "access_token_encrypted",
                            "refresh_token_encrypted",
                            "access_token_expires_at",
                            "provider_scopes",
                            "provider_account_id",
                            "connection_generation",
                            "authorization_placeholder",
                            "status",
                            "updated_at",
                        ],
                    )
            except IntegrityError as exc:
                if is_provider_account_ownership_conflict(exc):
                    raise ValueError(
                        GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT
                    ) from exc
                raise
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
            using = router.db_for_write(GarminConnection, instance=connection)
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

    using = router.db_for_write(GarminConnection, instance=connection)
    return _refresh_access_token_with_retry(connection, using)


def _reject_external_account_claim(
    *,
    provider: str,
    provider_account_id: str,
    exclude_pk: int,
    using: str,
) -> None:
    """Reject claims on an account already owned by another connection.

    The unique constraint remains the final arbiter under concurrency; this
    pre-check inside the atomic block guarantees a deterministic redacted
    error for sequential cross-user collisions without leaking ownership.
    """
    if not provider_account_id:
        return
    claimed_by_other = (
        GarminConnection.objects.using(using)
        .filter(
            provider=provider,
            provider_account_id=provider_account_id,
        )
        .exclude(pk=exclude_pk)
        .exists()
    )
    if claimed_by_other:
        raise ValueError(GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT)


def _claim_provider_account_id(
    *,
    connection_pk: int,
    provider_account_id: str,
    expected_generation: int,
    expected_provider_account_id: str,
    using: str,
) -> tuple[int, str]:
    """Atomically claim the first authoritative activity account identity."""
    with transaction.atomic(using=using):
        current = (
            GarminConnection.objects.using(using)
            .select_for_update(of=("self",))
            .get(pk=connection_pk)
        )
        if not current.is_active:
            raise ValueError("Garmin connection is not active")
        if (
            current.connection_generation != expected_generation
            or current.provider_account_id != expected_provider_account_id
        ):
            if current.provider_account_id == provider_account_id:
                return (
                    current.connection_generation,
                    current.provider_account_id,
                )
            raise ValueError("Garmin connection state changed during sync")
        if current.provider_account_id:
            if current.provider_account_id != provider_account_id:
                raise ValueError("Garmin connection state changed during sync")
            return current.connection_generation, current.provider_account_id

        _reject_external_account_claim(
            provider=current.provider,
            provider_account_id=provider_account_id,
            exclude_pk=current.pk,
            using=using,
        )
        current.provider_account_id = provider_account_id
        current.connection_generation += 1
        try:
            with transaction.atomic(using=using):
                current.save(
                    using=using,
                    update_fields=[
                        "provider_account_id",
                        "connection_generation",
                        "updated_at",
                    ],
                )
        except IntegrityError as exc:
            if is_provider_account_ownership_conflict(exc):
                raise ValueError(
                    GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT
                ) from exc
            raise
        return current.connection_generation, current.provider_account_id


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


def _normalized_from_persisted_activity(
    activity: GarminActivity,
) -> NormalizedActivity:
    """Snapshot provider provenance before a correction mutates its row."""
    return NormalizedActivity(
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
    )


def _ensure_exercise(
    garmin_activity: GarminActivity,
    *,
    day: Day,
    activity: NormalizedActivity,
    previous_activity: NormalizedActivity,
    previous_day_id: int | None,
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

    if exercise.type != Exercise.EXERCISE_CYCLE:
        return

    if not _is_garmin_derived_exercise(
        exercise=exercise,
        activity=previous_activity,
        linked_day_id=previous_day_id,
    ):
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

    using = router.db_for_write(GarminConnection, instance=connection)
    config = _provider_config()

    (
        access_token,
        expected_generation,
        expected_provider_account_id,
    ) = _ensure_access_token(connection)

    def _raw_activity_stream() -> Iterator[object]:
        """Advance the lazy provider iterator with one forced-refresh retry."""
        nonlocal access_token
        nonlocal expected_generation
        nonlocal expected_provider_account_id

        yielded_before_retry: list[object] = []
        retried = False
        replay_index = 0

        while True:
            try:
                raw_activities = iter(
                    _iter_activity_payloads(
                        access_token,
                        max_pages=int(config["activity_max_pages"]),
                        page_limit=int(config["activities_limit"]),
                        timeout=float(config["request_timeout"]),
                        activities_url=str(config["activities_url"]),
                        response_max_bytes=int(
                            config["activity_response_max_bytes"]
                        ),
                        activity_max_total_items=int(
                            config["activity_max_total_items"]
                        ),
                        activity_total_response_max_bytes=int(
                            config["activity_total_response_max_bytes"]
                        ),
                    )
                )
                while True:
                    raw_activity = next(raw_activities)
                    if retried and replay_index < len(yielded_before_retry):
                        if raw_activity != yielded_before_retry[replay_index]:
                            raise ValueError(
                                "Garmin activity pagination changed during retry"
                            )
                        replay_index += 1
                        continue
                    if not retried:
                        yielded_before_retry.append(raw_activity)
                    yield raw_activity
            except StopIteration:
                if retried and replay_index < len(yielded_before_retry):
                    raise ValueError(
                        "Garmin activity pagination changed during retry"
                    )
                return
            except ValueError as exc:
                if retried or "Garmin activity fetch unauthorized" not in str(
                    exc
                ):
                    raise
                (
                    access_token,
                    expected_generation,
                    expected_provider_account_id,
                ) = _ensure_access_token(connection, force_refresh=True)
                retried = True
                replay_index = 0

    imported = 0
    duplicates = 0
    unsupported = 0
    invalid = 0

    batch_size = int(config["activity_batch_size"])
    if batch_size <= 0:
        batch_size = 1

    connection_model_pk = connection.pk

    def _flush_batch(
        batch: dict[tuple[str, str], NormalizedActivity],
    ) -> tuple[int, int, int, int]:
        imported_count = 0
        duplicates_count = 0
        unsupported_count = 0
        invalid_count = 0

        if not batch:
            return (
                imported_count,
                duplicates_count,
                unsupported_count,
                invalid_count,
            )

        batch_filters = Q()
        for provider_account_id, provider_activity_id in batch:
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

            _ = lock_user_for_garmin_sync(
                using=using,
                user_id=connection.user_id,
            )
            if not connection.is_active:
                raise ValueError("Garmin connection is not active")
            if (
                connection.connection_generation != expected_generation
                or connection.provider_account_id
                != expected_provider_account_id
            ):
                raise ValueError("Garmin connection state changed during sync")

            resolved_batch: dict[
                tuple[str, str],
                tuple[NormalizedActivity, Day | None, str],
            ] = {}
            for key, normalized in batch.items():
                resolve_error = ""
                normalized_day = None
                if normalized.started_at_local_date is not None:
                    try:
                        normalized_day = _resolve_day_for_activity(
                            connection,
                            normalized.started_at_local_date,
                            using=using,
                        )
                    except ValueError:
                        resolve_error = (
                            _PENDING_RECONCILIATION_REASON_AMBIGUOUS_DAY
                        )

                pending_reason = _determine_pending_reason(
                    normalized_day,
                    normalized,
                    resolve_error,
                )
                resolved_batch[key] = (
                    normalized,
                    normalized_day,
                    pending_reason,
                )

            resolved_existing = {
                (row.provider_account_id, row.provider_activity_id): row
                for row in GarminActivity.objects.using(using)
                .select_for_update(of=("self",))
                .filter(connection=connection)
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
                if exercise is not None and exercise.day_id is not None:
                    day_ids.add(exercise.day_id)

            for _, normalized_day, pending_reason in resolved_batch.values():
                if normalized_day is not None and not pending_reason:
                    day_ids.add(normalized_day.pk)

            locks = (
                lock_plan_aggregate_rows(
                    using=using,
                    day_ids=tuple(sorted(day_ids)),
                )
                if day_ids
                else None
            )
            locked_days = locks.days_by_pk if locks is not None else {}

            try:
                for key, (
                    normalized,
                    normalized_day,
                    pending_reason,
                ) in resolved_batch.items():
                    provider_account_id = key[0]
                    resolved_day = (
                        None
                        if normalized_day is None
                        else locked_days.get(normalized_day.pk)
                    )

                    existing = resolved_existing.get(key)
                    if existing is None:
                        garmin_activity = GarminActivity.objects.db_manager(
                            using
                        ).create(
                            connection=connection,
                            provider_activity_id=normalized.provider_activity_id,
                            provider_activity_type=normalized.provider_activity_type,
                            provider_account_id=provider_account_id,
                            day=resolved_day,
                            provider_local_started_date=(
                                normalized.started_at_local_date
                            ),
                            provider_local_started_time=(
                                normalized.started_at_local_time
                            ),
                            provider_timezone_offset_minutes=(
                                normalized.provider_timezone_offset_minutes
                            ),
                            started_at=normalized.started_at,
                            kcals=normalized.kcals,
                            duration_seconds=normalized.duration_seconds,
                            distance=normalized.distance,
                            pending_reconciliation=bool(pending_reason),
                            pending_reconciliation_reason=pending_reason,
                        )
                        imported_count += 1
                        if resolved_day is not None:
                            _ensure_exercise(
                                garmin_activity,
                                day=resolved_day,
                                activity=normalized,
                                previous_activity=normalized,
                                previous_day_id=resolved_day.pk,
                                using=using,
                            )
                        continue

                    garmin_activity = existing
                    previous_day_id = garmin_activity.day_id
                    previous_activity = _normalized_from_persisted_activity(
                        garmin_activity
                    )
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
                    garmin_activity.provider_account_id = provider_account_id
                    garmin_activity.day = (
                        resolved_day if not pending_reason else None
                    )
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

                    retired_day_id = None
                    if pending_reason:
                        retired_day_id = _retire_garmin_derived_exercise(
                            garmin_activity=garmin_activity,
                            activity=previous_activity,
                            linked_day_id=previous_day_id,
                            using=using,
                        )
                        if retired_day_id is not None:
                            garmin_activity.exercise = None

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
                    duplicates_count += 1

                    if pending_reason:
                        if retired_day_id is not None:
                            _recompute_days_from_locked_rows(
                                locked_days,
                                {retired_day_id},
                                using=using,
                            )
                        continue

                    if resolved_day is None:
                        raise ValueError(
                            "Garmin activity day resolution is inconsistent"
                        )

                    _ensure_exercise(
                        garmin_activity,
                        day=resolved_day,
                        activity=normalized,
                        previous_activity=previous_activity,
                        previous_day_id=previous_day_id,
                        using=using,
                    )

                    lock_day_ids: set[int] = {resolved_day.pk}
                    if previous_day_id is not None:
                        lock_day_ids.add(previous_day_id)
                    if previous_exercise_day_id is not None:
                        lock_day_ids.add(previous_exercise_day_id)
                    _recompute_days_from_locked_rows(
                        locked_days,
                        lock_day_ids,
                        using=using,
                    )
            finally:
                if locks is not None:
                    locks.clear_markers()

        return (
            imported_count,
            duplicates_count,
            unsupported_count,
            invalid_count,
        )

    try:
        pending_batch: dict[tuple[str, str], NormalizedActivity] = {}
        batch_candidates = 0
        for raw_activity in _raw_activity_stream():
            try:
                normalized = _normalize_activity(raw_activity)
            except ValueError:
                invalid += 1
                continue

            provider_account_id = normalized.provider_account_id
            if not provider_account_id:
                invalid += 1
                continue
            if not expected_provider_account_id:
                (
                    expected_generation,
                    expected_provider_account_id,
                ) = _claim_provider_account_id(
                    connection_pk=connection_model_pk,
                    provider_account_id=provider_account_id,
                    expected_generation=expected_generation,
                    expected_provider_account_id=expected_provider_account_id,
                    using=using,
                )
                connection.connection_generation = expected_generation
                connection.provider_account_id = expected_provider_account_id
            elif provider_account_id != expected_provider_account_id:
                invalid += 1
                continue

            if normalized.provider_activity_type != _ACTIVITY_TYPE_CYCLE:
                unsupported += 1
                continue

            pending_batch[
                (provider_account_id, normalized.provider_activity_id)
            ] = normalized
            batch_candidates += 1
            if batch_candidates >= batch_size:
                (
                    imported_delta,
                    duplicates_delta,
                    unsupported_delta,
                    invalid_delta,
                ) = _flush_batch(pending_batch)
                imported += imported_delta
                duplicates += duplicates_delta
                unsupported += unsupported_delta
                invalid += invalid_delta
                pending_batch = {}
                batch_candidates = 0

        if pending_batch:
            (
                imported_delta,
                duplicates_delta,
                unsupported_delta,
                invalid_delta,
            ) = _flush_batch(pending_batch)
            imported += imported_delta
            duplicates += duplicates_delta
            unsupported += unsupported_delta
            invalid += invalid_delta

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
        if is_provider_account_ownership_conflict(exc):
            raise ValueError(
                GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT
            ) from exc
        raise ValueError("Garmin activity import failed") from exc
    except ValueError as exc:
        if (
            "Garmin connection state changed during sync" in str(exc)
            or str(exc) == GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT
        ):
            raise
        raise ValueError("Garmin activity import failed") from exc

    return GarminSyncSummary(
        imported=imported,
        duplicates=duplicates,
        unsupported=unsupported,
        invalid=invalid,
    )


def reconcile_pending_garmin_activities(connection: GarminConnection) -> int:
    """Attempt to reconcile unmatched valid provenance activities."""
    using = router.db_for_write(GarminConnection, instance=connection)

    reconciled = 0
    with transaction.atomic(using=using):
        connection = (
            GarminConnection.objects.using(using)
            .select_for_update(of=("self",))
            .get(pk=connection.pk)
        )
        if not connection.is_active:
            raise ValueError("Garmin connection is not active")

        _ = lock_user_for_garmin_sync(
            using=using,
            user_id=connection.user_id,
        )

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

            previous_exercise_day_id = (
                Exercise.objects.using(using)
                .filter(pk=activity.exercise_id)
                .values_list("day_id", flat=True)
                .first()
                if activity.exercise_id is not None
                else None
            )
            previous_day_id = activity.day_id
            previous_activity = _normalized_from_persisted_activity(activity)

            lock_day_ids: set[int] = {
                row_id
                for row_id in (previous_day_id, previous_exercise_day_id)
                if row_id is not None
            }
            if day is not None:
                lock_day_ids.add(day.pk)

            locked_rows = (
                lock_plan_aggregate_rows(
                    using=using,
                    day_ids=tuple(sorted(lock_day_ids)),
                )
                if lock_day_ids
                else None
            )
            locked_days = (
                locked_rows.days_by_pk if locked_rows is not None else {}
            )

            retired_day_id = None
            if day is not None:
                day = locked_days[day.pk]
                activity.day = day
            else:
                activity.day = None
                if activity.exercise_id is not None:
                    retired_day_id = _retire_garmin_derived_exercise(
                        garmin_activity=activity,
                        activity=previous_activity,
                        linked_day_id=previous_day_id,
                        using=using,
                    )
                    if retired_day_id is not None:
                        activity.exercise = None

            activity.pending_reconciliation = bool(pending_reason)
            activity.pending_reconciliation_reason = pending_reason
            activity.save(
                using=using,
                update_fields=[
                    "day",
                    "exercise",
                    "pending_reconciliation",
                    "pending_reconciliation_reason",
                ],
            )

            if retired_day_id is not None and locked_rows is not None:
                _recompute_days_from_locked_rows(
                    locked_days,
                    {retired_day_id},
                    using=using,
                )

            if not pending_reason:
                if day is None:
                    raise ValueError(
                        "Pending Garmin activity day resolution is inconsistent"
                    )
                _ensure_exercise(
                    activity,
                    day=day,
                    activity=previous_activity,
                    previous_activity=previous_activity,
                    previous_day_id=previous_day_id,
                    using=using,
                )
                if locked_rows is not None:
                    _recompute_days_from_locked_rows(
                        locked_days,
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
            # Empty strings are storage sentinels, not credentials.
            Q(access_token_encrypted__gt=_EMPTY_CIPHERTEXT)
            | Q(refresh_token_encrypted__gt=_EMPTY_CIPHERTEXT)
        )
    )

    results: dict[int, GarminSyncSummary] = {}
    for connection in query.order_by("pk"):
        try:
            results[connection.pk] = sync_connection(connection)
        except ValueError:
            continue
    return results
