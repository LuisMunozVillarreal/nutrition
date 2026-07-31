"""Garmin provider service and sync orchestration."""

from __future__ import annotations

import datetime
import math
import secrets
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, Q, router, transaction
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.plans.locks import lock_plan_aggregate_rows
from apps.plans.models import Day

from .models import (
    GARMIN_PROVIDER,
    GarminActivity,
    GarminConnection,
    GarminOAuthState,
)

_ACTIVITY_TYPE_CYCLE = "cycle"
_ACTIVITY_TYPE_CYCLING = {"cycle", "cycling", "bicycling", "bike", "bicycle", "biking"}
_ACTIVITY_CALORIES_MAX = 10_000_000
_ACTIVITY_DISTANCE_MAX = Decimal("99999999.99")
_ACTIVITY_DURATION_MAX_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class GarminTokenPair:
    """Normalized token exchange response."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str | None
    provider_account_id: str | None


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
    kcals: int
    duration_seconds: int
    distance: Decimal
    provider_account_id: str


def _required_setting(name: str) -> str:
    value = getattr(settings, name, "")
    if not value:
        raise ValueError(f"GARMIN setting {name} is required")
    return str(value)


def _required_positive_int(name: str) -> int:
    value = getattr(settings, name, None)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"GARMIN setting {name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"GARMIN setting {name} must be positive")
    return parsed


def _provider_config() -> dict[str, str | int]:
    """Load and validate Garmin settings when integration is enabled."""
    if not bool(getattr(settings, "GARMIN_ENABLED", False)):
        raise ValueError("Garmin integration is disabled")

    config = {
        "client_id": _required_setting("GARMIN_CLIENT_ID"),
        "client_secret": _required_setting("GARMIN_CLIENT_SECRET"),
        "authorization_url": _required_setting("GARMIN_AUTHORIZATION_URL"),
        "token_url": _required_setting("GARMIN_TOKEN_URL"),
        "activities_url": _required_setting("GARMIN_ACTIVITIES_URL"),
        "callback_url": _required_setting("GARMIN_CALLBACK_URL"),
        "scopes": _required_setting("GARMIN_SCOPES"),
        "request_timeout": _required_positive_int("GARMIN_REQUEST_TIMEOUT_SECONDS"),
        "activities_limit": _required_positive_int("GARMIN_ACTIVITIES_LIMIT"),
        "activity_max_pages": _required_positive_int("GARMIN_ACTIVITY_MAX_PAGES"),
        "state_ttl_seconds": _required_positive_int("GARMIN_STATE_TTL_SECONDS"),
    }
    return config


def _request_headers() -> dict[str, str]:
    """Common request headers for Garmin endpoints."""
    return {"Accept": "application/json"}


def _request_json(
    method: str,
    url: str,
    operation: str,
    *,
    timeout: float,
    **kwargs: object,
) -> dict[str, object]:
    """Perform a single typed request and validate a dict JSON body."""
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise ValueError(f"Garmin {operation} failed") from exc

    if response.status_code >= 400:
        raise ValueError(f"Garmin {operation} failed")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(f"Garmin {operation} returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Garmin {operation} returned invalid JSON")
    return payload


def begin_authorization(user) -> tuple[str, datetime.datetime, str]:
    """Generate a short-lived one-time state and authorization URL."""
    config = _provider_config()
    state = secrets.token_urlsafe(24)
    expires_at = timezone.now() + datetime.timedelta(
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
        raise ValueError("Garmin token response has invalid expires_in") from exc
    if not math.isfinite(expires_in_float) or expires_in_float < 0:
        raise ValueError("Garmin token response has invalid expires_in")

    refresh_token = payload.get("refresh_token")
    refresh_token_value = (
        str(refresh_token) if isinstance(refresh_token, str) and refresh_token else None
    )

    scope = payload.get("scope")
    scope_value = str(scope) if isinstance(scope, str) else None

    provider_account_id = payload.get("userId")
    provider_account_id_value = (
        str(provider_account_id) if provider_account_id is not None else None
    )

    return GarminTokenPair(
        access_token=access_token,
        refresh_token=refresh_token_value,
        expires_in=int(expires_in_float),
        scope=scope_value,
        provider_account_id=provider_account_id_value,
    )


def exchange_code_for_tokens(code: str) -> GarminTokenPair:
    """Exchange authorization code for a token pair."""
    if not code:
        raise ValueError("Garmin authorization code is required")

    config = _provider_config()
    response = _request_json(
        "POST",
        str(config["token_url"]),
        "token exchange",
        timeout=float(config["request_timeout"]),
        headers=_request_headers(),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config["callback_url"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
    )

    return _parse_token_payload(response)


def refresh_access_token(connection: GarminConnection) -> GarminTokenPair:
    """Refresh access token for an existing Garmin connection."""
    if not connection.refresh_token:
        raise ValueError("Garmin refresh token is missing")

    config = _provider_config()
    response = _request_json(
        "POST",
        str(config["token_url"]),
        "token refresh",
        timeout=float(config["request_timeout"]),
        headers=_request_headers(),
        data={
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
    )

    token = _parse_token_payload(response)
    if token.refresh_token is None:
        return GarminTokenPair(
            access_token=token.access_token,
            refresh_token=connection.refresh_token,
            expires_in=token.expires_in,
            scope=token.scope,
            provider_account_id=token.provider_account_id,
        )
    return token


def _ensure_access_token(connection: GarminConnection) -> str:
    """Refresh and persist access token when expired."""
    using = router.db_for_write(type(connection), instance=connection)
    if connection.access_token and connection.is_connected:
        return connection.access_token

    token = refresh_access_token(connection)
    connection.set_tokens(token, expires_in=token.expires_in)
    connection.save(
        using=using,
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_scopes",
            "provider_account_id",
            "updated_at",
        ]
    )
    if not connection.access_token:
        raise ValueError("Garmin access token is unavailable")
    return connection.access_token


def _coerce_started_at(value: object) -> datetime.datetime:
    """Parse a timezone-aware start time from Garmin payload."""
    if isinstance(value, datetime.datetime):
        dt = value
    elif isinstance(value, int | float):
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError("start time is invalid")
        if seconds > 10**12:
            seconds /= 1000
        dt = datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
    elif isinstance(value, str):
        if value.strip().replace(".", "", 1).replace("+", "", 1).isdigit():
            return _coerce_started_at(float(value))
        normalized = value.replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("start time is invalid") from exc
    else:
        raise ValueError("start time is invalid")

    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("start time must include timezone")
    return dt


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


def _validate_duration_seconds(seconds: int) -> int:
    if not isinstance(seconds, int):
        raise ValueError("duration_seconds out of supported bounds")
    if seconds < 0:
        raise ValueError("duration_seconds must be non-negative")
    if seconds > _ACTIVITY_DURATION_MAX_SECONDS:
        raise ValueError("duration_seconds out of supported bounds")
    duration = datetime.timedelta(seconds=seconds)
    try:
        Exercise._meta.get_field("duration").clean(duration, None)
    except ValidationError as exc:
        raise ValueError("duration_seconds out of supported bounds") from exc
    return seconds


def _validate_kcals(raw_kcals: object) -> int:
    kcals = _coerce_non_negative_int(raw_kcals, "kcal")
    if kcals > _ACTIVITY_CALORIES_MAX:
        raise ValueError("kcal out of supported bounds")
    try:
        Exercise._meta.get_field("kcals").clean(kcals, None)
    except ValidationError as exc:
        raise ValueError("kcal out of supported bounds") from exc
    return kcals


def _validate_distance_km(raw_distance: object, raw_unit: object) -> Decimal:
    distance = _coerce_decimal(raw_distance, "distance")
    if distance > _ACTIVITY_DISTANCE_MAX:
        raise ValueError("distance out of supported bounds")

    unit = str(raw_unit or "km").lower().strip()
    if unit in {"m", "meter", "meters", "metre", "metres"}:
        distance = distance / Decimal("1000")

    try:
        return Exercise._meta.get_field("distance").clean(distance, None)
    except ValidationError as exc:
        raise ValueError("distance out of supported bounds") from exc


def _normalize_activity(payload: object) -> NormalizedActivity:
    if not isinstance(payload, dict):
        raise ValueError("activity payload is invalid")

    raw_activity_id = payload.get("activityId")
    if raw_activity_id is None:
        raw_activity_id = payload.get("activity_id")
    if raw_activity_id is None:
        raise ValueError("activityId is missing")
    provider_activity_id = str(raw_activity_id)

    raw_activity_type = payload.get("activityType") or payload.get("activity_type")
    if raw_activity_type is None:
        raise ValueError("activityType is missing")
    provider_activity_type = str(raw_activity_type).strip().lower()
    if provider_activity_type not in _ACTIVITY_TYPE_CYCLING:
        provider_activity_type = provider_activity_type or ""

    started_at_value = (
        payload.get("startTime")
        or payload.get("start_time")
        or payload.get("startTimeInSeconds")
    )
    started_at = _coerce_started_at(started_at_value)

    duration_seconds = _coerce_non_negative_int(
        payload.get("duration")
        or payload.get("durationSeconds")
        or payload.get("duration_seconds")
        or 0,
        "duration",
    )
    _validate_duration_seconds(duration_seconds)

    kcals = _validate_kcals(
        payload.get("activeKcal")
        or payload.get("activeKilocalories")
        or payload.get("calories")
        or 0
    )
    distance = _validate_distance_km(
        payload.get("distance")
        or payload.get("distanceKm")
        or payload.get("distance_km")
        or payload.get("distanceMeters")
        or 0,
        payload.get("distanceUnit"),
    )

    raw_provider_account_id = payload.get("userId")
    provider_account_id = (
        str(raw_provider_account_id) if raw_provider_account_id is not None else ""
    )

    return NormalizedActivity(
        provider_activity_id=provider_activity_id,
        provider_activity_type=_ACTIVITY_TYPE_CYCLE
        if provider_activity_type in _ACTIVITY_TYPE_CYCLING
        else provider_activity_type,
        started_at=started_at,
        kcals=kcals,
        duration_seconds=duration_seconds,
        distance=distance,
        provider_account_id=provider_account_id,
    )


def _extract_activity_items(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload.get("activities")
    if raw is None:
        raw = payload.get("items")
    if raw is None:
        raw = payload.get("data")
    if raw is None and isinstance(payload.get("data"), dict):
        nested = payload["data"]
        if isinstance(nested, dict):
            raw = nested.get("activities")
    if not isinstance(raw, list):
        raise ValueError("Garmin activities payload is invalid")
    return [item for item in raw if isinstance(item, dict)]


def _extract_next_cursor(payload: dict[str, object]) -> str | None:
    cursor = payload.get("next") or payload.get("nextCursor") or payload.get("cursor")
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
) -> list[dict[str, object]]:
    """Fetch and iterate Garmin activities across paginated endpoints."""
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
            headers={
                **_request_headers(),
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
            raise ValueError("Garmin activity pagination exceeded maximum pages")

    return payloads


def _resolve_day_for_activity(
    connection: GarminConnection,
    activity: NormalizedActivity,
    *,
    using: str,
) -> Day | None:
    local_started_at = timezone.localtime(activity.started_at)
    return (
        Day.objects.using(using)
        .filter(day=local_started_at.date(), plan__user=connection.user)
        .select_related("plan")
        .first()
    )


def _exercise_time(activity: NormalizedActivity) -> datetime.time:
    return timezone.localtime(activity.started_at).time()


def _ensure_exercise(
    garmin_activity: GarminActivity,
    day: Day,
    activity: NormalizedActivity,
    *,
    using: str,
) -> None:
    """Attach or create an exercise row from a Garmin activity row."""
    if garmin_activity.exercise_id is not None:
        return

    exercise_time = _exercise_time(activity)

    existing = (
        Exercise.objects.using(using)
        .select_for_update(of=("self",))
        .filter(
            day=day,
            time=exercise_time,
            type=Exercise.EXERCISE_CYCLE,
        )
        .first()
    )
    if existing is not None:
        garmin_activity.exercise = existing
        garmin_activity.day = day
        garmin_activity.save(
            using=using,
            update_fields=["exercise", "day"],
        )
        return

    exercise = Exercise.objects.using(using).create(
        day=day,
        time=exercise_time,
        type=Exercise.EXERCISE_CYCLE,
        kcals=activity.kcals,
        duration=datetime.timedelta(seconds=activity.duration_seconds),
        distance=activity.distance,
    )
    garmin_activity.exercise = exercise
    garmin_activity.day = day
    garmin_activity.save(using=using, update_fields=["exercise", "day"])


def sync_connection(connection: GarminConnection) -> GarminSyncSummary:
    """Import Garmin activities for a connection and return a summary."""
    if not isinstance(connection, GarminConnection):
        raise TypeError("connection must be GarminConnection")

    if not connection.user_id:
        raise ValueError("Garmin connection is missing user")
    using = router.db_for_write(type(connection), instance=connection)
    config = _provider_config()

    access_token = _ensure_access_token(connection)
    raw_activities = _iter_activity_payloads(
        access_token,
        max_pages=int(config["activity_max_pages"]),
        page_limit=int(config["activities_limit"]),
        timeout=float(config["request_timeout"]),
        activities_url=str(config["activities_url"]),
    )

    imported = 0
    duplicates = 0
    unsupported = 0
    invalid = 0
    # De-duplicate repeated activity IDs before import attempts.
    candidate_activities: dict[str, tuple[int, NormalizedActivity]] = {}

    for raw_activity in raw_activities:
        try:
            normalized = _normalize_activity(raw_activity)
        except ValueError:
            invalid += 1
            continue

        if normalized.provider_activity_type != _ACTIVITY_TYPE_CYCLE:
            unsupported += 1
            continue

        day = _resolve_day_for_activity(connection, normalized, using=using)
        if day is None:
            invalid += 1
            continue

        if (
            day.pk is not None
            and normalized.provider_activity_id not in candidate_activities
        ):
            candidate_activities[normalized.provider_activity_id] = (
                day.pk,
                normalized,
            )

    day_ids = tuple(sorted(entry[0] for entry in candidate_activities.values()))
    locks = None

    try:
        with transaction.atomic(using=using):
            connection = GarminConnection.objects.using(using).select_for_update().get(
                pk=connection.pk
            )
            if day_ids:
                locks = lock_plan_aggregate_rows(using=using, day_ids=day_ids)

            for day_pk, normalized in candidate_activities.values():
                if locks is None:
                    day = Day.objects.using(using).get(pk=day_pk)
                else:
                    day = locks.days_by_pk[day_pk]
                started_at_utc = timezone.localtime(normalized.started_at).astimezone(
                    datetime.timezone.utc
                )
                garmin_activity_query = (
                    GarminActivity.objects.using(using)
                    .select_for_update(of=("self",))
                    .filter(
                        connection=connection,
                        provider_activity_id=normalized.provider_activity_id,
                    )
                )

                garmin_activity = garmin_activity_query.first()
                if garmin_activity is None:
                    try:
                        garmin_activity = GarminActivity.objects.using(using).create(
                            connection=connection,
                            provider_activity_id=normalized.provider_activity_id,
                            provider_activity_type=normalized.provider_activity_type,
                            provider_account_id=normalized.provider_account_id,
                            day=day,
                            started_at=started_at_utc,
                            kcals=normalized.kcals,
                            duration_seconds=normalized.duration_seconds,
                            distance=normalized.distance,
                        )
                        imported += 1
                    except IntegrityError as exc:
                        if not garmin_activity_query.using(using).exists():
                            raise ValueError(
                                "Garmin activity import failed"
                            ) from exc
                        garmin_activity = garmin_activity_query.using(using).get()
                        duplicates += 1
                else:
                    duplicates += 1
                    garmin_activity.provider_activity_type = (
                        normalized.provider_activity_type
                    )
                    garmin_activity.provider_account_id = normalized.provider_account_id
                    garmin_activity.day = day
                    garmin_activity.started_at = started_at_utc
                    garmin_activity.kcals = normalized.kcals
                    garmin_activity.duration_seconds = normalized.duration_seconds
                    garmin_activity.distance = normalized.distance
                    garmin_activity.save(
                        using=using,
                        update_fields=[
                            "provider_activity_type",
                            "provider_account_id",
                            "day",
                            "started_at",
                            "kcals",
                            "duration_seconds",
                            "distance",
                        ],
                    )

                _ensure_exercise(
                    garmin_activity,
                    day=day,
                    activity=normalized,
                    using=using,
                )
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
    finally:
        if locks is not None:
            locks.clear_markers()

    return GarminSyncSummary(
        imported=imported,
        duplicates=duplicates,
        unsupported=unsupported,
        invalid=invalid,
    )


def sync_all_connections() -> dict[int, GarminSyncSummary]:
    """Sync every currently connected Garmin connection."""
    if not bool(getattr(settings, "GARMIN_ENABLED", False)):
        return {}

    query = GarminConnection.objects.filter(
        Q(access_token_encrypted__gt="")
        & (
            Q(access_token_expires_at__isnull=True)
            | Q(access_token_expires_at__gt=timezone.now())
        )
    )

    results: dict[int, GarminSyncSummary] = {}
    for connection in query.order_by("pk"):
        try:
            results[connection.pk] = sync_connection(connection)
        except ValueError:
            continue
    return results
