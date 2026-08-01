"""Garmin service layer tests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, router
from django.utils import timezone

import apps.garmin.services as services
from apps.exercises.models import Exercise
from apps.garmin.models import (
    GarminActivity,
    GarminConnection,
    GarminOAuthState,
)
from apps.garmin.services import GarminSyncSummary
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan

User = get_user_model()


def _configure_garmin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GARMIN_ENABLED", True)
    monkeypatch.setattr(settings, "GARMIN_CLIENT_ID", "garmin-client-id")
    monkeypatch.setattr(settings, "GARMIN_CLIENT_SECRET", "garmin-secret")
    monkeypatch.setattr(
        settings, "GARMIN_AUTHORIZATION_URL", "https://garmin.example.com/auth"
    )
    monkeypatch.setattr(
        settings, "GARMIN_TOKEN_URL", "https://garmin.example.com/token"
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_ACTIVITIES_URL",
        "https://garmin.example.com/activities",
    )
    monkeypatch.setattr(
        settings, "GARMIN_CALLBACK_URL", "https://app.example.com/callback"
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_PROVIDER_ORIGINS",
        ["https://garmin.example.com"],
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_CALLBACK_ALLOWED_ORIGINS",
        ["https://app.example.com"],
    )
    monkeypatch.setattr(settings, "GARMIN_SCOPES", "read write")
    monkeypatch.setattr(settings, "GARMIN_REQUEST_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_PAGES", 3)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITIES_LIMIT", 100)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_TOTAL_ITEMS", 10000)
    monkeypatch.setattr(
        settings,
        "GARMIN_ACTIVITY_ENDPOINT_MAX_TOTAL_BYTES",
        5 * 1024 * 1024,
    )
    monkeypatch.setattr(settings, "GARMIN_STATE_TTL_SECONDS", 300)
    monkeypatch.setattr(settings, "GARMIN_TOKEN_MAX_TTL_SECONDS", 3600)
    monkeypatch.setattr(
        settings,
        "GARMIN_ACTIVITY_ENDPOINT_MAX_RESPONSE_BYTES",
        1024 * 1024,
    )
    monkeypatch.setattr(
        settings,
        "GARMIN_TOKEN_ENDPOINT_MAX_RESPONSE_BYTES",
        512 * 1024,
    )
    monkeypatch.setattr(
        settings, "GARMIN_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


def _create_user(email: str):
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


def _create_user_with_day(email: str) -> tuple[Any, Day]:
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


def _connection_with_token(
    user: Any, *, access_token: str = "access-token"
) -> GarminConnection:
    connection = GarminConnection.objects.create(user=user)
    token_pair = services.GarminTokenPair(
        access_token=access_token,
        refresh_token="refresh-token",
        expires_in=3600,
        scope="read write",
        provider_account_id="provider-user",
    )
    connection.set_tokens(token_pair, expires_in=token_pair.expires_in)
    connection.save(
        update_fields=[
            "access_token_encrypted",
            "refresh_token_encrypted",
            "access_token_expires_at",
            "provider_account_id",
            "provider_scopes",
            "connection_generation",
        ]
    )
    return connection


class _FakeStreamingResponse:
    """Minimal streaming response shim for request-level byte-limit tests."""

    def __init__(
        self,
        *,
        status_code: int,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
        encoding: str = "utf-8",
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.headers = headers or {}
        self.encoding = encoding
        self.closed = False

    def iter_content(self, chunk_size: int = 1):  # noqa: ARG002
        for chunk in self._chunks:
            yield chunk

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_FakeStreamingResponse":
        return self

    def __exit__(self, *args) -> None:  # noqa: ARG002
        self.close()


def _activity_payload(
    *,
    activity_id: str,
    activity_type: str,
    started_at: str,
    start_time_local: str | None = None,
    distance: object = 12.5,
    distance_unit: str | None = "km",
    distance_source: str | None = None,
    user_id: str = "provider-user",
    include_local_fields: bool = True,
    duration: int = 30,
) -> dict:
    local = start_time_local if start_time_local is not None else started_at
    payload: dict[str, object] = {
        "activityId": activity_id,
        "activityType": activity_type,
        "startTime": started_at,
        "duration": 30,
        "activeKcal": 120,
        "userId": user_id,
    }
    if include_local_fields:
        payload["startTimeLocal"] = local
    if distance_unit is not None:
        payload["distanceUnit"] = distance_unit
    if distance_source == "distanceMiles":
        payload["distanceMiles"] = distance
    elif distance_source == "distanceMeters":
        payload["distanceMeters"] = distance
    else:
        payload["distance"] = distance

    if include_local_fields and start_time_local is None:
        payload["timezoneOffsetMinutes"] = 0
    payload["duration"] = duration

    return payload


def test_iter_activity_payloads_follows_cursors(requests_mock, monkeypatch):
    """Pagination must follow cursor pages and stop on terminal page."""
    _configure_garmin(monkeypatch)

    requests_mock.get(
        "https://garmin.example.com/activities",
        [
            {
                "json": {
                    "activities": [
                        _activity_payload(
                            activity_id="1",
                            activity_type="cycle",
                            started_at="2026-08-01T10:00:00+00:00",
                        ),
                    ],
                    "next": "cursor-2",
                },
            },
            {
                "json": {
                    "activities": [
                        _activity_payload(
                            activity_id="2",
                            activity_type="cycle",
                            started_at="2026-08-01T10:30:00+00:00",
                        ),
                    ]
                }
            },
        ],
    )

    payloads = services._iter_activity_payloads(
        "access-token",
        max_pages=3,
        page_limit=100,
        timeout=10.0,
        activities_url="https://garmin.example.com/activities",
        response_max_bytes=1024 * 1024,
        activity_max_total_items=100,
    )

    assert [row["activityId"] for row in payloads] == ["1", "2"]


def test_iter_activity_payloads_detects_loop(requests_mock, monkeypatch):
    """A repeated cursor should fail fast to avoid infinite loops."""
    _configure_garmin(monkeypatch)

    requests_mock.get(
        "https://garmin.example.com/activities",
        [
            {
                "json": {
                    "activities": [
                        _activity_payload(
                            activity_id="1",
                            activity_type="cycle",
                            started_at="2026-08-01T10:00:00+00:00",
                        )
                    ],
                    "next": "cursor",
                }
            },
            {
                "json": {
                    "activities": [
                        _activity_payload(
                            activity_id="2",
                            activity_type="cycle",
                            started_at="2026-08-01T11:00:00+00:00",
                        )
                    ],
                    "next": "cursor",
                }
            },
        ],
    )

    with pytest.raises(
        ValueError, match="Garmin activity pagination loop detected"
    ):
        list(
            services._iter_activity_payloads(
                "access-token",
                max_pages=3,
                page_limit=100,
                timeout=10.0,
                activities_url="https://garmin.example.com/activities",
                response_max_bytes=1024 * 1024,
                activity_max_total_items=100,
            )
        )


def test_iter_activity_payloads_exceeds_max_pages(requests_mock, monkeypatch):
    """Configured page limit must prevent unbounded cursor loops."""
    _configure_garmin(monkeypatch)

    requests_mock.get(
        "https://garmin.example.com/activities",
        [
            {
                "json": {
                    "activities": [
                        _activity_payload(
                            activity_id="1",
                            activity_type="cycle",
                            started_at="2026-08-01T10:00:00+00:00",
                        )
                    ],
                    "next": "cursor",
                }
            },
        ],
    )

    with pytest.raises(
        ValueError, match="Garmin activity pagination exceeded maximum pages"
    ):
        list(
            services._iter_activity_payloads(
                "access-token",
                max_pages=1,
                page_limit=100,
                timeout=10.0,
                activities_url="https://garmin.example.com/activities",
                response_max_bytes=1024 * 1024,
                activity_max_total_items=100,
            )
        )


def test_iter_activity_payloads_is_lazy_per_page(monkeypatch):
    """Payload consumption should request pages only as needed."""
    _configure_garmin(monkeypatch)

    calls: list[tuple[int | None, dict[str, str]]] = []
    request_index = 0

    def _iter(
        _method: str,
        _url: str,
        _operation: str,
        *,
        timeout: float,
        max_response_bytes: int,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
    ) -> tuple[dict[str, object], int]:
        nonlocal request_index
        calls.append((max_response_bytes, dict(params or {})))
        if request_index == 0:
            request_index += 1
            return {
                "activities": [
                    _activity_payload(
                        activity_id="1",
                        activity_type="cycle",
                        started_at="2026-08-01T10:00:00+00:00",
                    ),
                    _activity_payload(
                        activity_id="2",
                        activity_type="cycle",
                        started_at="2026-08-01T10:10:00+00:00",
                    ),
                ],
                "next": "page-2",
            }, 16
        if request_index == 1:
            request_index += 1
            return {
                "activities": [
                    _activity_payload(
                        activity_id="3",
                        activity_type="cycle",
                        started_at="2026-08-01T11:00:00+00:00",
                    )
                ]
            }, 8
        raise AssertionError("unexpected page request")

    monkeypatch.setattr(services, "_request_json_with_size", _iter)

    iterator = services._iter_activity_payloads(
        "access-token",
        max_pages=3,
        page_limit=100,
        timeout=10.0,
        activities_url="https://garmin.example.com/activities",
        response_max_bytes=1024 * 1024,
        activity_max_total_items=10,
    )
    assert len(calls) == 0

    first_item = next(iterator)
    assert first_item["activityId"] == "1"
    assert len(calls) == 1

    assert [row["activityId"] for row in iterator] == ["2", "3"]
    assert len(calls) == 2


def test_iter_activity_payloads_respects_aggregate_limits(monkeypatch):
    """Aggregate item/byte limits should stop streaming mid-stream."""
    _configure_garmin(monkeypatch)

    payloads = [
        (
            {
                "activities": [
                    _activity_payload(
                        activity_id="1",
                        activity_type="cycle",
                        started_at="2026-08-01T10:00:00+00:00",
                    ),
                    _activity_payload(
                        activity_id="2",
                        activity_type="cycle",
                        started_at="2026-08-01T10:05:00+00:00",
                    ),
                ],
                "next": "page-2",
            },
            4,
        ),
        (
            {
                "activities": [
                    _activity_payload(
                        activity_id="3",
                        activity_type="cycle",
                        started_at="2026-08-01T10:10:00+00:00",
                    )
                ]
            },
            4,
        ),
    ]
    request_index = 0

    def _iter(*_, **__) -> tuple[dict[str, object], int]:
        nonlocal request_index
        payload, response_bytes = payloads[request_index]
        request_index += 1
        return payload, response_bytes

    monkeypatch.setattr(services, "_request_json_with_size", _iter)

    iterator = services._iter_activity_payloads(
        "access-token",
        max_pages=3,
        page_limit=100,
        timeout=10.0,
        activities_url="https://garmin.example.com/activities",
        response_max_bytes=1024 * 1024,
        activity_max_total_items=2,
        activity_total_response_max_bytes=100,
    )
    with pytest.raises(
        ValueError,
        match="Garmin activity payloads exceeded total item limit",
    ):
        list(iterator)

    assert request_index == 2


def test_iter_activity_payloads_respects_aggregate_response_limit(monkeypatch):
    """The total streamed response budget should bound all fetched pages."""
    _configure_garmin(monkeypatch)

    payloads = [
        (
            {
                "activities": [
                    _activity_payload(
                        activity_id="1",
                        activity_type="cycle",
                        started_at="2026-08-01T10:00:00+00:00",
                    )
                ],
                "next": "page-2",
            },
            8,
        ),
        (
            {
                "activities": [
                    _activity_payload(
                        activity_id="2",
                        activity_type="cycle",
                        started_at="2026-08-01T10:10:00+00:00",
                    )
                ]
            },
            8,
        ),
    ]
    request_index = 0

    def _iter(*_, **__) -> tuple[dict[str, object], int]:
        nonlocal request_index
        payload, response_bytes = payloads[request_index]
        request_index += 1
        return payload, response_bytes

    monkeypatch.setattr(services, "_request_json_with_size", _iter)

    iterator = services._iter_activity_payloads(
        "access-token",
        max_pages=3,
        page_limit=100,
        timeout=10.0,
        activities_url="https://garmin.example.com/activities",
        response_max_bytes=1024 * 1024,
        activity_max_total_items=10,
        activity_total_response_max_bytes=10,
    )
    with pytest.raises(
        ValueError,
        match="Garmin activity responses exceeded total byte limit",
    ):
        list(iterator)

    assert request_index == 2


def test_iter_activity_payloads_extracts_nested_data_payloads(
    requests_mock, monkeypatch
):
    """Nested provider payload shapes should be supported."""
    _configure_garmin(monkeypatch)

    nested_activity = _activity_payload(
        activity_id="nested-1",
        activity_type="cycle",
        started_at="2026-08-01T10:00:00+00:00",
    )

    requests_mock.get(
        "https://garmin.example.com/activities",
        [
            {
                "json": {
                    "data": {
                        "activities": [nested_activity],
                    }
                }
            },
        ],
    )

    payloads = list(
        services._iter_activity_payloads(
            "access-token",
            max_pages=1,
            page_limit=100,
            timeout=10.0,
            activities_url="https://garmin.example.com/activities",
            response_max_bytes=1024 * 1024,
            activity_max_total_items=100,
        )
    )

    assert len(payloads) == 1
    assert payloads[0]["activityId"] == "nested-1"


def test_refresh_access_token_preserves_refresh_token_if_missing(monkeypatch):
    """Token refresh must remain usable without a provider refresh token."""
    _configure_garmin(monkeypatch)
    user = _create_user("refresh-preserve@example.com")
    connection = _connection_with_token(user)

    monkeypatch.setattr(
        services,
        "_request_json",
        lambda *_, **__: {
            "access_token": "rotated-access",
            "expires_in": 1800,
        },
    )

    token = services.refresh_access_token(connection)

    assert token.access_token == "rotated-access"
    assert token.refresh_token == "refresh-token"


def test_refresh_access_token_with_retry_stores_rotated_refresh_token(
    monkeypatch,
):
    """A rotated refresh token from the provider should be persisted."""
    _configure_garmin(monkeypatch)
    user = _create_user("refresh-rotate-persist@example.com")
    connection = _connection_with_token(user)

    using = router.db_for_write(type(connection), instance=connection)

    def _refresh(
        _connection: services.GarminConnection,
    ) -> services.GarminTokenPair:
        return services.GarminTokenPair(
            access_token="rotated-access",
            refresh_token="rotated-refresh",
            expires_in=1800,
            scope="read write",
            provider_account_id="provider-user",
        )

    monkeypatch.setattr(services, "refresh_access_token", _refresh)

    access_token, _, _ = services._refresh_access_token_with_retry(
        connection,
        using,
    )

    connection.refresh_from_db()
    assert access_token == "rotated-access"
    assert connection.refresh_token == "rotated-refresh"


def test_refresh_access_token_with_retry_preserves_refresh_on_missing(
    monkeypatch,
):
    """Omitted rotate refresh token should keep the previous value."""
    _configure_garmin(monkeypatch)
    user = _create_user("refresh-rotate-omit@example.com")
    connection = _connection_with_token(
        user,
        access_token="stale-access",
    )

    using = router.db_for_write(type(connection), instance=connection)

    def _refresh(
        _connection: services.GarminConnection,
    ) -> services.GarminTokenPair:
        return services.GarminTokenPair(
            access_token="rotated-access",
            refresh_token=None,
            expires_in=1800,
            scope="read write",
            provider_account_id="provider-user",
        )

    monkeypatch.setattr(services, "refresh_access_token", _refresh)

    access_token, _, _ = services._refresh_access_token_with_retry(
        connection,
        using,
    )

    connection.refresh_from_db()
    assert access_token == "rotated-access"
    assert connection.refresh_token == "refresh-token"


def test_sync_connection_counts_imports_unsupported_invalid_and_owned_days(
    monkeypatch,
):
    """Sync only attaches to user-owned days.

    It also counts unsupported and invalid activities.
    """
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-owned@example.com")
    connection = _connection_with_token(user)

    orphaned_day_date = day.day + timedelta(days=14)

    payloads = [
        _activity_payload(
            activity_id="owned-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
        ),
        _activity_payload(
            activity_id="orphan-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(orphaned_day_date, datetime.min.time())
            ).isoformat(),
        ),
        {
            "activityId": "unsupported-1",
            "activityType": "walk",
            "startTime": "2026-08-01T12:00:00+00:00",
            "startTimeLocal": "2026-08-01T12:00:00+00:00",
            "timezoneOffsetMinutes": 0,
            "duration": 40,
            "activeKcal": 400,
            "distance": 3.3,
            "distanceUnit": "km",
            "userId": "provider-user",
        },
        {
            "activityId": "invalid-1",
            "activityType": "cycle",
        },
    ]

    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=2,
        duplicates=0,
        unsupported=1,
        invalid=1,
    )
    imported = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="owned-1",
    )
    assert imported.day == day
    pending = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="orphan-1",
    )
    assert pending.pending_reconciliation is True
    assert pending.day is None


def test_sync_connection_stores_unmatched_activity_without_day_as_pending(
    monkeypatch,
):
    """Persist unmatched activities with no day.

    Queue them for later matching.
    """
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-pending@example.com")
    connection = _connection_with_token(user)

    missing_day = day.day + timedelta(days=60)

    payloads = [
        _activity_payload(
            activity_id="pending-day-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(missing_day, datetime.min.time())
            ).isoformat(),
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )
    activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="pending-day-1",
    )
    assert activity.day is None
    assert activity.pending_reconciliation is True

    measurement = Measurement.objects.create(
        user=user,
        weight=Decimal("80.0"),
        body_fat_perc=Decimal("20.0"),
    )
    WeekPlan.objects.create(
        user=user,
        measurement=measurement,
        start_date=missing_day,
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=500,
    )
    assert services.reconcile_pending_garmin_activities(connection) == 1

    activity.refresh_from_db()
    assert activity.day is not None
    assert activity.day.day == missing_day
    assert activity.pending_reconciliation is False
    assert activity.exercise is not None


def test_sync_connection_is_idempotent_for_duplicate_payload_ids(monkeypatch):
    """Repeated provider IDs resolve as duplicates for the same connection."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-dup@example.com")
    connection = _connection_with_token(user)

    GarminActivity.objects.create(
        connection=connection,
        provider_activity_id="dup-1",
        provider_activity_type="cycle",
        provider_account_id="provider-user",
        day=day,
        started_at=timezone.now(),
        kcals=1,
        duration_seconds=10,
        distance=Decimal("1.0"),
    )

    payloads = [
        _activity_payload(
            activity_id="dup-1",
            activity_type="cycle",
            started_at="2026-08-01T10:00:00+00:00",
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=0,
        duplicates=1,
        unsupported=0,
        invalid=0,
    )
    assert (
        GarminActivity.objects.filter(
            connection=connection,
            provider_activity_id="dup-1",
        ).count()
        == 1
    )


def test_sync_connection_rejects_ambiguous_day_matches(monkeypatch):
    """Treat overlapping plans for a day as ambiguous."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-ambiguous@example.com")
    connection = _connection_with_token(user)

    second_measurement = Measurement.objects.create(
        user=user,
        weight=Decimal("80.0"),
        body_fat_perc=Decimal("20.0"),
    )
    WeekPlan.objects.create(
        user=user,
        measurement=second_measurement,
        start_date=day.day,
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=500,
    )

    payloads = [
        _activity_payload(
            activity_id="ambiguous-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )
    activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="ambiguous-1",
    )
    assert activity.day is None
    assert activity.exercise is None
    assert activity.pending_reconciliation is True
    assert activity.pending_reconciliation_reason == "ambiguous_day"


def test_sync_connection_uses_locked_day_for_new_activity(monkeypatch):
    """Cached candidate day metadata should not be used for writes."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-locked-day-service@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="locked-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
        )
    ]
    monkeypatch.setattr(
        services,
        "_iter_activity_payloads",
        lambda *_, **__: payloads,
    )

    captured: dict[str, object] = {}
    uses_locked_day: list[bool] = []
    using = router.db_for_write(services.GarminActivity)
    manager = services.GarminActivity.objects.db_manager(using)
    original_create = type(manager).create
    original_lock_plan = services.lock_plan_aggregate_rows

    def _track_lock(*, using: str, day_ids: tuple[int, ...], plan_ids=()):
        locked = original_lock_plan(
            using=using,
            day_ids=day_ids,
            plan_ids=plan_ids,
        )
        captured["locked_days"] = locked.days_by_pk
        return locked

    original_day_save = services.Day.save

    def _track_day_save(instance: services.Day, *args, **kwargs):
        uses_locked_day.append(
            getattr(instance, "_plan_aggregate_locks", None) is not None
        )
        return original_day_save(instance, *args, **kwargs)

    def _track_create(*_self, **kwargs):
        captured["activity_day"] = kwargs.get("day")
        return original_create(manager, **kwargs)

    monkeypatch.setattr(services, "lock_plan_aggregate_rows", _track_lock)
    monkeypatch.setattr(type(manager), "create", _track_create)
    monkeypatch.setattr(services.Day, "save", _track_day_save)

    services.sync_connection(connection)
    captured["uses_locked_day"] = uses_locked_day

    created_day = captured["activity_day"]
    locked_days = captured["locked_days"]
    assert isinstance(created_day, services.Day)
    assert created_day is locked_days[day.pk]
    assert captured.get("uses_locked_day")
    assert all(captured["uses_locked_day"])


def test_sync_connection_reconciles_moved_exercise_and_recomputes_days(
    monkeypatch,
):
    """Date changes should move exercise and refresh both day states."""
    _configure_garmin(monkeypatch)
    user, source_day = _create_user_with_day("sync-move-exercise@example.com")
    target_day = WeekPlan.objects.create(
        user=user,
        measurement=Measurement.objects.create(
            user=user,
            weight=Decimal("80.0"),
            body_fat_perc=Decimal("20.0"),
        ),
        start_date=source_day.day + timedelta(days=3),
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=500,
    ).days.first()
    assert target_day is not None
    connection = _connection_with_token(user)
    lock_calls: list[tuple[int, ...]] = []
    original_lock_plan = services.lock_plan_aggregate_rows

    def _track_lock(*, using: str, day_ids: tuple[int, ...], plan_ids=()):
        lock_calls.append(tuple(sorted(day_ids)))
        return original_lock_plan(
            using=using,
            day_ids=day_ids,
            plan_ids=plan_ids,
        )

    monkeypatch.setattr(services, "lock_plan_aggregate_rows", _track_lock)

    existing_exercise = services.Exercise.objects.create(
        day=source_day,
        time=time(9, 0),
        type=services.Exercise.EXERCISE_CYCLE,
        kcals=120,
        duration=timedelta(minutes=30),
        distance=Decimal("5.00"),
    )
    GarminActivity.objects.create(
        connection=connection,
        provider_activity_id="move-1",
        provider_activity_type="cycle",
        provider_account_id="provider-user",
        day=source_day,
        exercise=existing_exercise,
        provider_local_started_date=source_day.day,
        provider_local_started_time=time(9, 0),
        provider_timezone_offset_minutes=0,
        started_at=timezone.make_aware(
            datetime.combine(source_day.day, time(9, 0))
        ),
        kcals=120,
        duration_seconds=1800,
        distance=Decimal("5.00"),
    )

    payloads = [
        _activity_payload(
            activity_id="move-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(target_day.day, time(9, 0))
            ).isoformat(),
            duration=1800,
        )
    ]
    monkeypatch.setattr(
        services,
        "_iter_activity_payloads",
        lambda *_, **__: payloads,
    )

    services.sync_connection(connection)

    source_day.refresh_from_db()
    target_day.refresh_from_db()
    assert source_day.energy_kcal == Decimal("0.00")
    assert target_day.energy_kcal == Decimal("0.00")
    assert source_day.exercises.count() == 0
    assert target_day.exercises.count() == 1

    activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="move-1",
    )
    assert activity.day_id == target_day.pk
    assert activity.exercise is not None
    assert activity.exercise.day_id == target_day.pk
    assert tuple(sorted((source_day.pk, target_day.pk))) in lock_calls


def test_sync_connection_ambiguous_day_reconciles_after_resolution(
    monkeypatch,
):
    """Ambiguous matches recover after ambiguity resolves."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-ambiguous-recover@example.com")
    connection = _connection_with_token(user)

    second_measurement = Measurement.objects.create(
        user=user,
        weight=Decimal("80.0"),
        body_fat_perc=Decimal("20.0"),
    )
    overlapping_plan = WeekPlan.objects.create(
        user=user,
        measurement=second_measurement,
        start_date=day.day,
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=500,
    )

    payloads = [
        _activity_payload(
            activity_id="ambiguous-recover-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
        )
    ]
    monkeypatch.setattr(
        services,
        "_iter_activity_payloads",
        lambda *_, **__: payloads,
    )

    summary = services.sync_connection(connection)
    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )
    activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="ambiguous-recover-1",
    )
    assert activity.day is None
    assert activity.exercise is None
    assert activity.pending_reconciliation_reason == "ambiguous_day"
    assert activity.pending_reconciliation is True

    overlapping_plan.delete()

    assert services.reconcile_pending_garmin_activities(connection) == 1

    activity.refresh_from_db()
    assert activity.pending_reconciliation is False
    assert activity.day is not None
    assert activity.day.day == day.day
    assert activity.exercise is not None


def test_sync_connection_resolved_activity_retries_after_becoming_ambiguous(
    monkeypatch,
):
    """Resolved Garmin imports retire their derived exercise through ambiguity."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-ambiguous-cycle@example.com")
    connection = _connection_with_token(user)
    started_at = timezone.make_aware(datetime.combine(day.day, time(8, 30)))
    manual_exercise = Exercise.objects.create(
        day=day,
        time=time(7, 30),
        type=Exercise.EXERCISE_WALK,
        kcals=40,
        duration=timedelta(minutes=30),
        distance=Decimal("1.00"),
    )

    payload = [
        _activity_payload(
            activity_id="ambiguous-cycle-1",
            activity_type="cycle",
            started_at=started_at.isoformat(),
            distance=Decimal("12.00"),
        )
    ]
    monkeypatch.setattr(
        services,
        "_iter_activity_payloads",
        lambda *_, **__: payload,
    )

    first_summary = services.sync_connection(connection)
    assert first_summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )
    first_activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="ambiguous-cycle-1",
    )
    assert first_activity.exercise is not None
    assert first_activity.pending_reconciliation is False
    day.refresh_from_db()
    assert sum(day.exercises.values_list("kcals", flat=True)) == 160
    assert manual_exercise.pk is not None

    overlapping_measurement = Measurement.objects.create(
        user=user,
        weight=Decimal("80.0"),
        body_fat_perc=Decimal("20.0"),
    )
    overlapping_plan = WeekPlan.objects.create(
        user=user,
        measurement=overlapping_measurement,
        start_date=day.day,
        protein_g_kg=Decimal("1.8"),
        fat_perc=Decimal("25.0"),
        deficit=500,
    )

    second_summary = services.sync_connection(connection)
    assert second_summary == GarminSyncSummary(
        imported=0,
        duplicates=1,
        unsupported=0,
        invalid=0,
    )

    first_activity.refresh_from_db()
    assert first_activity.pending_reconciliation is True
    assert first_activity.pending_reconciliation_reason == "ambiguous_day"
    assert first_activity.exercise is None
    manual_exercise.refresh_from_db()
    day.refresh_from_db()
    assert sum(day.exercises.values_list("kcals", flat=True)) == 40
    assert (
        Exercise.objects.filter(
            day=day,
            type=Exercise.EXERCISE_CYCLE,
            kcals=120,
            distance=Decimal("12.00"),
        ).count()
        == 0
    )

    overlapping_plan.delete()
    assert services.reconcile_pending_garmin_activities(connection) == 1

    first_activity.refresh_from_db()
    assert first_activity.pending_reconciliation is False
    assert first_activity.exercise is not None
    day.refresh_from_db()
    assert sum(day.exercises.values_list("kcals", flat=True)) == 160
    assert (
        Exercise.objects.filter(
            day=day,
            type=Exercise.EXERCISE_CYCLE,
            kcals=120,
            distance=Decimal("12.00"),
        ).count()
        == 1
    )
    assert Exercise.objects.filter(
        pk=manual_exercise.pk,
        day=day,
        type=Exercise.EXERCISE_WALK,
    ).exists()


def test_sync_connection_quantizes_meters_before_validation(monkeypatch):
    """Quantize raw meter distances.

    Conversion rounds to exercise precision.
    """
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-distance-meters@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="distance-meters-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
            distance_source="distanceMeters",
            distance=Decimal("12345"),
        ),
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )
    activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="distance-meters-1",
    )
    assert activity.distance == Decimal("12.35")


def test_sync_connection_rejects_provider_account_mismatch(monkeypatch):
    """Provider rows for a different Garmin account should not import."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-account-mismatch@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="account-mismatch-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
            user_id="other-account",
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=0,
        duplicates=0,
        unsupported=0,
        invalid=1,
    )
    assert not GarminActivity.objects.filter(
        connection=connection,
        provider_activity_id="account-mismatch-1",
    ).exists()


def test_sync_connection_rejects_unknown_distance_unit(monkeypatch):
    """A distance without parseable units must be rejected as invalid."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-distance-unit@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="distance-unknown-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
            distance_unit="furlongs",
        ),
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=0,
        duplicates=0,
        unsupported=0,
        invalid=1,
    )


@pytest.mark.parametrize("unit", ["mi", "mile", "miles"])
def test_sync_connection_converts_distance_miles_unit_to_kilometers(
    monkeypatch, unit: str
):
    """Distance miles should normalize to kilometers."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-distance-mile-unit@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="distance-mile-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
            distance_source="distanceMiles",
            distance=Decimal("1.234"),
            distance_unit=unit,
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )
    activity = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="distance-mile-1",
    )
    assert activity.distance == Decimal("1.99")


def test_sync_connection_rejects_distance_miles_with_kilometer_unit(
    monkeypatch,
):
    """A mileage source with a non-mile unit should be rejected."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day(
        "sync-distance-mile-unit-contradiction@example.com"
    )
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="distance-mile-contradiction-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
            distance_source="distanceMiles",
            distance=Decimal("1.0"),
            distance_unit="km",
        )
    ]

    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=0,
        duplicates=0,
        unsupported=0,
        invalid=1,
    )


def test_validate_distance_km_rejects_miles_out_of_bounds():
    """Miles distances should retain existing kilometer-level bounds."""
    max_miles = (
        services._ACTIVITY_DISTANCE_MAX
        / services._ACTIVITY_DISTANCE_MILES_TO_KM
    )

    assert services._validate_distance_km(
        Decimal("1"), "mile", source="distanceMiles"
    ) == Decimal("1.61")

    assert services._validate_distance_km(
        max_miles,
        "mile",
        source="distanceMiles",
    ) == services._ACTIVITY_DISTANCE_MAX.quantize(
        services._ACTIVITY_DISTANCE_QUANT
    )

    with pytest.raises(ValueError, match="distance out of supported bounds"):
        services._validate_distance_km(
            max_miles + Decimal("0.000001"),
            "mile",
            source="distanceMiles",
        )


def test_sync_connection_rejects_payloads_missing_local_start(monkeypatch):
    """Local-start metadata must be explicit and not inferred from UTC."""
    _configure_garmin(monkeypatch)
    user, _day = _create_user_with_day("sync-missing-local@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="missing-local-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(_day.day, datetime.min.time())
            ).isoformat(),
            include_local_fields=False,
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=0,
        duplicates=0,
        unsupported=0,
        invalid=1,
    )


def test_sync_connection_rolls_back_on_activity_error(monkeypatch):
    """Any create failure must abort the run without persisted side-effects."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-rollback@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="fail-1",
            activity_type="cycle",
            started_at="2026-08-01T10:00:00+00:00",
        )
    ]
    monkeypatch.setattr(
        services, "_iter_activity_payloads", lambda *_, **__: payloads
    )

    def _never_create(*args, **kwargs):
        raise IntegrityError("broken")

    monkeypatch.setattr(
        type(services.GarminActivity.objects),
        "create",
        _never_create,
    )

    with pytest.raises(ValueError, match="Garmin activity import failed"):
        services.sync_connection(connection)

    connection.refresh_from_db()
    assert connection.last_synced_at is None
    assert GarminActivity.objects.filter(connection=connection).count() == 0


def test_state_ttl_enforces_expiry(monkeypatch):
    """Expired OAuth state rows should be rejected by model helper."""
    _configure_garmin(monkeypatch)
    user = _create_user("state-timeout@example.com")

    GarminOAuthState.create_for_user(
        user=user,
        raw_state="expired",
        provider="garmin",
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="OAuth state is expired"):
        GarminOAuthState.consume_for_user(
            user=user, raw_state="expired", provider="garmin"
        )


def test_begin_authorization_uses_router_alias_with_user_instance(
    monkeypatch,
):
    """Oauth state issuance must use user-sharded write alias."""
    _configure_garmin(monkeypatch)
    user = _create_user("begin-auth-router@example.com")

    captured_db_for_write: list[tuple[Any, object | None]] = []

    def _db_for_write(model, instance=None):
        captured_db_for_write.append((model, instance))
        return "default"

    monkeypatch.setattr(services.router, "db_for_write", _db_for_write)

    state_methods: dict[str, object] = {}

    original_prune = services.GarminOAuthState.prune_expired.__func__
    original_count = services.GarminOAuthState.count_active.__func__
    original_create = services.GarminOAuthState.create_for_user.__func__

    def _prune(
        cls,
        *,
        now,
        user: Any,
        provider: str,
        retention_seconds: int = 3600,
        using=None,
    ):
        state_methods["prune"] = using
        return original_prune(
            cls,
            now=now,
            user=user,
            provider=provider,
            retention_seconds=retention_seconds,
            using=using,
        )

    def _count(cls, *, now, user: Any, provider: str, using=None):
        state_methods["count"] = using
        return original_count(
            cls,
            now=now,
            user=user,
            provider=provider,
            using=using,
        )

    def _create(
        cls,
        user: Any,
        raw_state: str,
        *,
        provider: str,
        expires_at,
        using=None,
    ):
        state_methods["create"] = using
        return original_create(
            cls,
            user,
            raw_state,
            provider=provider,
            expires_at=expires_at,
            using=using,
        )

    monkeypatch.setattr(
        services.GarminOAuthState, "prune_expired", classmethod(_prune)
    )
    monkeypatch.setattr(
        services.GarminOAuthState, "count_active", classmethod(_count)
    )
    monkeypatch.setattr(
        services.GarminOAuthState, "create_for_user", classmethod(_create)
    )

    services.begin_authorization(user)

    assert captured_db_for_write
    assert all(
        db_model.__name__ == "GarminOAuthState" and db_instance is user
        for db_model, db_instance in captured_db_for_write
    )
    assert state_methods == {
        "prune": "default",
        "count": "default",
        "create": "default",
    }


def test_provider_config_rejects_unapproved_origin(monkeypatch):
    """Provider endpoints must be in a configured HTTPS origin allowlist."""
    _configure_garmin(monkeypatch)
    monkeypatch.setattr(
        settings,
        "GARMIN_AUTHORIZATION_URL",
        "https://auth.evil.example.com/auth",
    )

    with pytest.raises(ValueError, match="unapproved origin"):
        services._provider_config()


def test_provider_config_rejects_fragment_and_credentials(monkeypatch):
    """Provider callback URLs must not include credentials or fragment."""
    _configure_garmin(monkeypatch)
    monkeypatch.setattr(
        settings,
        "GARMIN_TOKEN_URL",
        "https://user:pass@garmin.example.com/token",
    )

    with pytest.raises(ValueError, match="credentials"):
        services._provider_config()

    monkeypatch.setattr(
        settings,
        "GARMIN_TOKEN_URL",
        "https://garmin.example.com/token#fragment",
    )

    with pytest.raises(ValueError, match="fragments"):
        services._provider_config()


def test_provider_config_rejects_revoke_url_outside_provider_origins(
    monkeypatch,
):
    """Optional revoke URL also follows provider origin policy."""
    _configure_garmin(monkeypatch)
    monkeypatch.setattr(
        settings,
        "GARMIN_REVOKE_TOKEN_URL",
        "https://revoke.evil.example.com/revoke",
    )

    with pytest.raises(ValueError, match="unapproved origin"):
        services._provider_config()


def test_parse_token_payload_accepts_provider_account_id_at_model_max_length(
    monkeypatch,
):
    """A provider account id at max length should remain valid payload."""
    _configure_garmin(monkeypatch)
    payload = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "userId": "x" * 255,
    }

    parsed = services._parse_token_payload(payload)

    assert parsed.provider_account_id == "x" * 255


def test_parse_token_payload_rejects_oversize_provider_account_id(monkeypatch):
    """Overlong provider account ids should raise instead of truncating."""
    _configure_garmin(monkeypatch)
    payload = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "userId": "x" * 256,
    }

    with pytest.raises(ValueError, match="provider_account_id is too long"):
        services._parse_token_payload(payload)


def test_parse_token_payload_rejects_collision_style_provider_account_ids(
    monkeypatch,
):
    """Two near-duplicate ids should both be rejected when over max length."""
    _configure_garmin(monkeypatch)

    first = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "userId": ("x" * 255 + "a"),
    }
    second = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "userId": ("x" * 255 + "b"),
    }

    with pytest.raises(ValueError, match="provider_account_id is too long"):
        services._parse_token_payload(first)
    with pytest.raises(ValueError, match="provider_account_id is too long"):
        services._parse_token_payload(second)


def test_request_json_enforces_exact_boundary_and_streaming(monkeypatch):
    """Streaming parser allows exact-boundary payloads and stream=True."""
    _configure_garmin(monkeypatch)
    captured: dict[str, object] = {}

    payload = b'{"ok": true}'
    fake_response = _FakeStreamingResponse(
        status_code=200,
        chunks=[payload],
        headers={},
    )

    def _request(*_, **kwargs) -> _FakeStreamingResponse:
        captured["stream"] = kwargs["stream"]
        return fake_response

    monkeypatch.setattr(services.requests, "request", _request)

    result = services._request_json(
        "GET",
        "https://garmin.example.com/activities",
        "activity fetch",
        timeout=10.0,
        max_response_bytes=len(payload),
    )

    assert captured["stream"] is True
    assert result == {"ok": True}
    assert fake_response.closed is True


def test_request_json_rejects_chunked_payloads_over_limit(monkeypatch):
    """Chunked bodies beyond the byte limit should be rejected quickly."""
    _configure_garmin(monkeypatch)
    payload = b'{"ok": "x"}'
    fake_response = _FakeStreamingResponse(
        status_code=200,
        chunks=[payload[:4], payload[4:]],
        headers={},
    )

    monkeypatch.setattr(
        services.requests,
        "request",
        lambda *_, **__: fake_response,
    )

    with pytest.raises(ValueError, match="exceeded limit"):
        services._request_json(
            "GET",
            "https://garmin.example.com/activities",
            "activity fetch",
            timeout=10.0,
            max_response_bytes=3,
        )
    assert fake_response.closed is True


def test_request_json_rejects_invalid_content_length(monkeypatch):
    """Invalid content-length headers should fail before parsing."""
    _configure_garmin(monkeypatch)
    fake_response = _FakeStreamingResponse(
        status_code=200,
        chunks=[b'{"ok": true}'],
        headers={"Content-Length": "n/a"},
    )
    monkeypatch.setattr(
        services.requests,
        "request",
        lambda *_, **__: fake_response,
    )

    with pytest.raises(ValueError, match="invalid content length"):
        services._request_json(
            "GET",
            "https://garmin.example.com/activities",
            "activity fetch",
            timeout=10.0,
            max_response_bytes=1024,
        )
    assert fake_response.closed is True


def test_request_json_exact_boundary_payload_is_accepted(monkeypatch):
    """An exact-boundary body should be parsed without truncation."""
    _configure_garmin(monkeypatch)
    payload = b'{"ok": true}'
    fake_response = _FakeStreamingResponse(
        status_code=200,
        chunks=[payload[:4], payload[4:]],
        headers={"Content-Length": str(len(payload))},
    )
    monkeypatch.setattr(
        services.requests,
        "request",
        lambda *_, **__: fake_response,
    )

    result = services._request_json(
        "GET",
        "https://garmin.example.com/activities",
        "activity fetch",
        timeout=10.0,
        max_response_bytes=len(payload),
    )

    assert result == {"ok": True}
    assert fake_response.closed is True


def test_request_json_rejects_redirect_status_codes(monkeypatch):
    """3xx responses must not be treated as successful response bodies."""
    _configure_garmin(monkeypatch)
    fake_response = _FakeStreamingResponse(
        status_code=302,
        chunks=[b'{"ok": true}'],
        headers={"Location": "https://garmin.example.com/login"},
    )
    monkeypatch.setattr(
        services.requests,
        "request",
        lambda *_, **__: fake_response,
    )

    with pytest.raises(ValueError, match="Garmin activity fetch failed"):
        services._request_json(
            "GET",
            "https://garmin.example.com/login",
            "activity fetch",
            timeout=10.0,
            max_response_bytes=1024,
        )

    assert fake_response.closed is True


def test_sync_connection_retries_fetch_with_forced_refresh_on_unauthorized(
    monkeypatch,
):
    """401 responses must trigger a forced token refresh before retrying."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-401-refresh@example.com")
    connection = _connection_with_token(user)

    payloads = [
        _activity_payload(
            activity_id="authorized-after-refresh",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
        )
    ]

    attempts: dict[str, int] = {"fetch": 0}

    def _iter(token: str, *_, **__) -> list[dict[str, object]]:
        attempts["fetch"] += 1
        if attempts["fetch"] == 1:
            raise ValueError("Garmin activity fetch unauthorized")
        if token != "refreshed-access":
            raise ValueError("Garmin activity fetch unauthorized")
        return payloads

    monkeypatch.setattr(services, "_iter_activity_payloads", _iter)

    refresh_calls = {"count": 0}

    def _refresh(_connection) -> services.GarminTokenPair:
        refresh_calls["count"] += 1
        return services.GarminTokenPair(
            access_token="refreshed-access",
            refresh_token="refresh-token",
            expires_in=3600,
            scope="read write",
            provider_account_id="provider-user",
        )

    monkeypatch.setattr(services, "refresh_access_token", _refresh)

    summary = services.sync_connection(connection)

    assert attempts["fetch"] == 2
    assert refresh_calls["count"] == 1
    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=0,
        invalid=0,
    )


def test_sync_connection_rejects_generation_change_before_import(monkeypatch):
    """Do not overwrite expected generation before remote fetch."""
    _configure_garmin(monkeypatch)
    user, day = _create_user_with_day("sync-generation-account@example.com")
    connection = _connection_with_token(user)
    connection.access_token_expires_at = timezone.now() - timedelta(hours=1)
    connection.save(update_fields=["access_token_expires_at"])

    payloads = [
        _activity_payload(
            activity_id="generated-1",
            activity_type="cycle",
            started_at=timezone.make_aware(
                datetime.combine(day.day, datetime.min.time())
            ).isoformat(),
        )
    ]

    def _refresh(_connection) -> services.GarminTokenPair:
        return services.GarminTokenPair(
            access_token="refreshed-access",
            refresh_token="refresh-token",
            expires_in=3600,
            scope="read write",
            provider_account_id=None,
        )

    monkeypatch.setattr(services, "refresh_access_token", _refresh)

    def _iter(*_, **__) -> list[dict[str, object]]:
        stale = GarminConnection.objects.get(pk=connection.pk)
        stale.provider_account_id = "rotated-account"
        stale.connection_generation += 1
        stale.save(
            update_fields=["provider_account_id", "connection_generation"]
        )
        return payloads

    monkeypatch.setattr(services, "_iter_activity_payloads", _iter)

    with pytest.raises(
        ValueError,
        match="Garmin connection state changed during sync",
    ):
        services.sync_connection(connection)

    assert (
        GarminActivity.objects.filter(
            connection=connection, provider_activity_id="generated-1"
        ).count()
        == 0
    )


def test_token_refresh_does_not_clear_last_sync_state_on_failed_import(
    monkeypatch,
):
    """Preserve sync metadata until a successful import writes new values."""
    _configure_garmin(monkeypatch)
    user, _day = _create_user_with_day("sync-preserve-metadata@example.com")
    connection = _connection_with_token(user)
    baseline = timezone.now() - timedelta(hours=1)
    connection.last_synced_at = baseline
    connection.last_sync_summary = {
        "imported": 3,
        "duplicates": 1,
        "unsupported": 1,
        "invalid": 0,
    }
    connection.access_token_expires_at = timezone.now() - timedelta(hours=1)
    connection.save(
        update_fields=[
            "last_synced_at",
            "last_sync_summary",
            "access_token_expires_at",
        ]
    )

    def _refresh(_connection) -> services.GarminTokenPair:
        return services.GarminTokenPair(
            access_token="refreshed-access",
            refresh_token="refresh-token",
            expires_in=3600,
            scope="read write",
            provider_account_id="provider-user",
        )

    monkeypatch.setattr(services, "refresh_access_token", _refresh)

    def _iter(*_, **__) -> list[dict[str, object]]:
        raise ValueError("broken")

    monkeypatch.setattr(services, "_iter_activity_payloads", _iter)

    with pytest.raises(ValueError, match="broken"):
        services.sync_connection(connection)

    connection.refresh_from_db()
    assert connection.last_synced_at == baseline
    assert connection.last_sync_summary == {
        "imported": 3,
        "duplicates": 1,
        "unsupported": 1,
        "invalid": 0,
    }
