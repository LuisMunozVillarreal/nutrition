"""Health Connect companion API acceptance tests."""

import datetime
import json
from types import SimpleNamespace

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from apps.exercises.models import DaySteps
from apps.health_sync.models import (
    HealthSyncDevice,
    HealthSyncPairingCode,
    StepImport,
)
from config.schema import schema


def bearer_context(user_id):
    """Build an authenticated GraphQL context for a user."""
    token = jwt.encode(
        {"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256"
    )
    request = SimpleNamespace(
        META={"HTTP_AUTHORIZATION": f"Bearer {token}"},
        user=None,
    )
    return SimpleNamespace(request=request)


def post_json(client, path, payload, token=None):
    """POST JSON to a health-sync endpoint."""
    headers = {}
    if token is not None:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client.post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


@pytest.mark.django_db
def test_pairing_code_is_shown_once_and_consumed_once(client, user_factory):
    """A short-lived code can mint exactly one scoped device token."""
    user = user_factory()
    result = schema.execute_sync(
        """
        mutation {
          createHealthSyncPairingCode { code expiresAt }
        }
        """,
        context_value=bearer_context(user.id),
    )

    assert result.errors is None
    code = result.data["createHealthSyncPairingCode"]["code"]
    assert len(code) == 12
    assert code.isdigit()
    assert not HealthSyncPairingCode.objects.filter(code_hash=code).exists()

    first = post_json(
        client,
        "/api/health-sync/pair/",
        {"code": code, "device_name": "Galaxy phone"},
    )
    assert first.status_code == 201
    body = first.json()
    assert body["token"].startswith("nhs_")
    assert body["device_name"] == "Galaxy phone"
    assert (
        HealthSyncDevice.objects.filter(user=user, revoked_at=None).count()
        == 1
    )

    replay = post_json(
        client,
        "/api/health-sync/pair/",
        {"code": code, "device_name": "Replay"},
    )
    assert replay.status_code == 400
    assert replay.json() == {"error": "Pairing code is invalid or expired"}


@pytest.mark.django_db
def test_pairing_code_emission_is_rate_limited_per_user(user_factory):
    """Repeated UI clicks cannot mint an unbounded stream of active codes."""
    user = user_factory()
    first = schema.execute_sync(
        "mutation { createHealthSyncPairingCode { code } }",
        context_value=bearer_context(user.id),
    )
    second = schema.execute_sync(
        "mutation { createHealthSyncPairingCode { code } }",
        context_value=bearer_context(user.id),
    )

    assert first.errors is None
    assert second.errors
    assert (
        HealthSyncPairingCode.objects.filter(
            user=user, consumed_at=None
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_step_upload_requires_a_valid_scoped_device_token(client):
    """The ingestion endpoint fails closed without a valid device credential."""
    payload = {"records": []}

    missing = post_json(client, "/api/health-sync/steps/", payload)
    invalid = post_json(
        client, "/api/health-sync/steps/", payload, "not-a-token"
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json() == {"error": "Authentication required"}
    assert invalid.json() == {"error": "Authentication required"}


@pytest.mark.django_db
def test_step_upload_creates_and_updates_day_steps_idempotently(
    client,
    user_factory,
    day_factory,
):
    """A newer Health Connect aggregate becomes the authoritative day total."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    raw_token, device = HealthSyncDevice.issue(user=user, name="Galaxy phone")

    first_observed = timezone.now() - datetime.timedelta(minutes=5)
    first = post_json(
        client,
        "/api/health-sync/steps/",
        {
            "records": [
                {
                    "date": timezone.localdate().isoformat(),
                    "steps": 12345,
                    "observed_at": first_observed.isoformat(),
                }
            ]
        },
        raw_token,
    )

    assert first.status_code == 200
    assert first.json()["summary"] == {
        "created": 1,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
    }
    day_steps = DaySteps.objects.get(day=day)
    assert day_steps.steps == 12345
    imported = StepImport.objects.get(day_steps=day_steps)
    assert imported.device == device
    assert imported.source == "health_connect"

    newer_observed = timezone.now()
    second = post_json(
        client,
        "/api/health-sync/steps/",
        {
            "records": [
                {
                    "date": timezone.localdate().isoformat(),
                    "steps": 13001,
                    "observed_at": newer_observed.isoformat(),
                }
            ]
        },
        raw_token,
    )
    replay = post_json(
        client,
        "/api/health-sync/steps/",
        {
            "records": [
                {
                    "date": timezone.localdate().isoformat(),
                    "steps": 13001,
                    "observed_at": newer_observed.isoformat(),
                }
            ]
        },
        raw_token,
    )

    assert second.json()["summary"]["updated"] == 1
    assert replay.json()["summary"]["unchanged"] == 1
    day_steps.refresh_from_db()
    assert day_steps.steps == 13001
    assert StepImport.objects.filter(day_steps=day_steps).count() == 1
    device.refresh_from_db()
    assert device.last_success_at is not None


@pytest.mark.django_db
def test_stale_step_upload_cannot_overwrite_a_newer_total(
    client,
    user_factory,
    day_factory,
):
    """Out-of-order background jobs cannot roll a day back."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    raw_token, _device = HealthSyncDevice.issue(user=user, name="Galaxy phone")
    newer = timezone.now()
    older = newer - datetime.timedelta(hours=1)

    for steps, observed_at in ((15000, newer), (10000, older)):
        response = post_json(
            client,
            "/api/health-sync/steps/",
            {
                "records": [
                    {
                        "date": timezone.localdate().isoformat(),
                        "steps": steps,
                        "observed_at": observed_at.isoformat(),
                    }
                ]
            },
            raw_token,
        )
        assert response.status_code == 200

    assert DaySteps.objects.get(day=day).steps == 15000


@pytest.mark.django_db
def test_upload_skips_dates_without_a_unique_day_for_the_token_owner(
    client,
    user_factory,
    day_factory,
):
    """Imports never attach to another user or guess between duplicate plan days."""
    owner = user_factory()
    other = user_factory()
    day_factory(
        plan__user=other, day=timezone.localdate() - datetime.timedelta(days=1)
    )
    day_factory(plan__user=owner, day=timezone.localdate())
    day_factory(plan__user=owner, day=timezone.localdate())
    raw_token, _device = HealthSyncDevice.issue(
        user=owner, name="Galaxy phone"
    )

    response = post_json(
        client,
        "/api/health-sync/steps/",
        {
            "records": [
                {
                    "date": (
                        timezone.localdate() - datetime.timedelta(days=1)
                    ).isoformat(),
                    "steps": 5000,
                    "observed_at": timezone.now().isoformat(),
                },
                {
                    "date": timezone.localdate().isoformat(),
                    "steps": 6000,
                    "observed_at": timezone.now().isoformat(),
                },
            ]
        },
        raw_token,
    )

    assert response.status_code == 200
    assert response.json()["summary"]["skipped"] == 2
    assert DaySteps.objects.count() == 0
    _device.refresh_from_db()
    assert _device.last_success_at is None


@pytest.mark.django_db
def test_revoked_device_token_is_rejected(client, user_factory):
    """Revocation immediately stops subsequent uploads."""
    user = user_factory()
    raw_token, device = HealthSyncDevice.issue(user=user, name="Galaxy phone")
    device.revoked_at = timezone.now()
    device.save(update_fields=["revoked_at"])

    response = post_json(
        client,
        "/api/health-sync/steps/",
        {"records": []},
        raw_token,
    )

    assert response.status_code == 401
