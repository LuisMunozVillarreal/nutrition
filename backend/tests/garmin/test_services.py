"""Garmin service layer tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

import apps.garmin.services as services
from apps.garmin.models import GarminActivity, GarminConnection, GarminOAuthState
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
    monkeypatch.setattr(settings, "GARMIN_TOKEN_URL", "https://garmin.example.com/token")
    monkeypatch.setattr(
        settings, "GARMIN_ACTIVITIES_URL", "https://garmin.example.com/activities"
    )
    monkeypatch.setattr(settings, "GARMIN_CALLBACK_URL", "https://app.example.com/callback")
    monkeypatch.setattr(settings, "GARMIN_SCOPES", "read write")
    monkeypatch.setattr(settings, "GARMIN_REQUEST_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITY_MAX_PAGES", 3)
    monkeypatch.setattr(settings, "GARMIN_ACTIVITIES_LIMIT", 100)
    monkeypatch.setattr(settings, "GARMIN_STATE_TTL_SECONDS", 300)
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


def _create_user_with_day(email: str) -> tuple[User, Day]:
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
    user: User, *, access_token: str = "access-token"
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
        ]
    )
    return connection


def _activity_payload(*, activity_id: str, activity_type: str, started_at: str) -> dict:
    return {
        "activityId": activity_id,
        "activityType": activity_type,
        "startTime": started_at,
        "duration": 30,
        "activeKcal": 250,
        "distance": 12.5,
        "distanceUnit": "km",
        "userId": "provider-user",
    }


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

    with pytest.raises(ValueError, match="Garmin activity pagination loop detected"):
        services._iter_activity_payloads(
            "access-token",
            max_pages=3,
            page_limit=100,
            timeout=10.0,
            activities_url="https://garmin.example.com/activities",
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
        services._iter_activity_payloads(
            "access-token",
            max_pages=1,
            page_limit=100,
            timeout=10.0,
            activities_url="https://garmin.example.com/activities",
        )


def test_refresh_access_token_preserves_refresh_token_if_missing(monkeypatch):
    """Token refresh must remain usable without a provider refresh token."""
    _configure_garmin(monkeypatch)
    user = _create_user("refresh-preserve@example.com")
    connection = _connection_with_token(user)

    monkeypatch.setattr(
        services,
        "_request_json",
        lambda *_, **__: {"access_token": "rotated-access", "expires_in": 1800},
    )

    token = services.refresh_access_token(connection)

    assert token.access_token == "rotated-access"
    assert token.refresh_token == "refresh-token"


def test_sync_connection_counts_imports_unsupported_invalid_and_owned_days(monkeypatch):
    """Sync must only attach activities to user-owned days and count anomalies."""
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

    monkeypatch.setattr(services, "_iter_activity_payloads", lambda *_, **__: payloads)

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=1,
        duplicates=0,
        unsupported=1,
        invalid=1,
    )
    imported = GarminActivity.objects.get(
        connection=connection,
        provider_activity_id="owned-1",
    )
    assert imported.day == day


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
    monkeypatch.setattr(services, "_iter_activity_payloads", lambda *_, **__: payloads)

    summary = services.sync_connection(connection)

    assert summary == GarminSyncSummary(
        imported=0,
        duplicates=1,
        unsupported=0,
        invalid=0,
    )
    assert GarminActivity.objects.filter(
        connection=connection,
        provider_activity_id="dup-1",
    ).count() == 1


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
    monkeypatch.setattr(services, "_iter_activity_payloads", lambda *_, **__: payloads)

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
