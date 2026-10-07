"""Browser authorization and silent renewal acceptance tests."""

import base64
import hashlib
from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from apps.health_sync.models import HealthSyncDevice, HealthSyncGrant

REDIRECT = "com.nutrition.healthsync:/oauth2redirect"
ISSUER = "https://testserver"
VERIFIER = "a" * 43


def post(client, action, payload, **headers):
    """Send the public JSON contract over HTTPS."""
    return client.post(
        f"/api/health-sync/{action}/",
        data=payload,
        content_type="application/json",
        secure=True,
        **headers,
    )


def authorize(client, user):
    """Authorize one explicit browser consent with the existing account JWT."""
    token = jwt.encode(
        {"sub": str(user.pk)}, settings.SECRET_KEY, algorithm="HS256"
    )
    return post(
        client,
        "authorize",
        {
            "redirect_uri": REDIRECT,
            "issuer": ISSUER,
            "code_challenge": base64.urlsafe_b64encode(
                hashlib.sha256(VERIFIER.encode()).digest()
            )
            .decode()
            .rstrip("="),
            "code_challenge_method": "S256",
            "state": "s" * 43,
            "device_name": "My phone",
        },
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_ORIGIN=ISSUER,
    )


@pytest.mark.django_db
def test_browser_consent_exchanges_one_code_for_scoped_credentials(
    client, user_factory
):
    """Only the originating PKCE client receives renewable sync credentials."""
    # Given explicit authenticated consent in the existing browser session
    user = user_factory()
    consent = authorize(client, user)
    assert consent.status_code == 201
    code = consent.json()["code"]
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": VERIFIER,
        "redirect_uri": REDIRECT,
        "issuer": ISSUER,
    }

    # When Android exchanges the code and proves possession of its verifier
    response = post(client, "token", payload)

    # Then it gets separate short-lived access and durable renewal credentials
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 900
    assert body["refresh_token"] != body["access_token"]
    assert body["scope"] == "health-sync:steps"
    assert response["Cache-Control"] == "no-store"
    assert HealthSyncDevice.authenticate(body["access_token"]).user == user
    assert HealthSyncDevice.authenticate(body["refresh_token"]) is None
    assert post(client, "token", payload).status_code == 400


@pytest.mark.django_db
def test_refresh_rotation_retries_and_revocation(client, user_factory):
    """Ambiguous network failures can retry without reviving older credentials."""
    # Given an expired access token with an active renewable device grant
    consent = authorize(client, user_factory()).json()
    tokens = post(
        client,
        "token",
        {
            "grant_type": "authorization_code",
            "code": consent["code"],
            "code_verifier": VERIFIER,
            "redirect_uri": REDIRECT,
            "issuer": ISSUER,
        },
    ).json()
    device = HealthSyncDevice.authenticate(tokens["access_token"])
    HealthSyncGrant.objects.filter(device=device).update(
        access_expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert HealthSyncDevice.authenticate(tokens["access_token"]) is None
    rotation = {
        "grant_type": "refresh_token",
        "issuer": ISSUER,
        "refresh_token": tokens["refresh_token"],
        "next_refresh_token": "n" * 43,
    }

    # When a durable, client-generated replacement is submitted and retried
    renewed = post(client, "token", rotation)
    retried = post(client, "token", rotation)

    # Then exactly the same credentials are returned and old access is rejected
    assert renewed.status_code == 200
    assert retried.json() == renewed.json()
    assert (
        HealthSyncDevice.authenticate(renewed.json()["access_token"]) == device
    )
    assert HealthSyncDevice.authenticate(tokens["access_token"]) is None
    replay = dict(rotation, next_refresh_token="x" * 43)
    assert post(client, "token", replay).status_code == 400
    second = dict(
        rotation, refresh_token="n" * 43, next_refresh_token="z" * 43
    )
    assert post(client, "token", second).status_code == 200
    assert post(client, "token", rotation).status_code == 400
    revoked = post(
        client,
        "revoke",
        {
            "issuer": ISSUER,
            "refresh_token": "z" * 43,
        },
    )
    assert revoked.status_code == 200
    assert post(client, "token", second).status_code == 400
    assert (
        HealthSyncDevice.authenticate(renewed.json()["access_token"]) is None
    )
