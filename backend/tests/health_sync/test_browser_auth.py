"""Browser authorization and silent renewal acceptance tests."""

import base64
import hashlib
from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.health_sync.models import (
    HealthSyncAuthorization,
    HealthSyncDevice,
    HealthSyncGrant,
)

REDIRECT = "com.nutrition.healthsync:/oauth2redirect"
ISSUER = "https://testserver"
VERIFIER = "a" * 43


@pytest.fixture(autouse=True)
def reset_limits():
    """Isolate endpoint rate counters between acceptance scenarios."""
    cache.clear()


def post(client, action, payload, **headers):
    """Send the public JSON contract over HTTPS."""
    return client.post(
        f"/api/health-sync/{action}/",
        data=payload,
        content_type="application/json",
        secure=True,
        **headers,
    )


def authorize(client, user, **overrides):
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
            **overrides,
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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [
        ("redirect_uri", []),
        ("redirect_uri", "https://evil.example.com/"),
        ("issuer", "https://other.example.com"),
        ("code_challenge_method", "plain"),
        ("code_challenge", "short"),
        ("state", "short"),
        ("device_name", None),
        ("device_name", ""),
        ("device_name", "x" * 121),
    ],
)
def test_invalid_consent_cannot_issue_a_code(
    client, user_factory, field, value
):
    """Reject malformed values, open redirects, and cross-environment grants."""
    # Given an authenticated account and an invalid consent parameter
    user = user_factory()
    # When the authorization is submitted
    response = authorize(client, user, **{field: value})
    # Then no authorization code is created
    assert response.status_code == 400
    assert not HealthSyncAuthorization.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("verifier", ["b" * 43, "short", None])
def test_wrong_pkce_does_not_consume_code(client, user_factory, verifier):
    """An interceptor cannot exchange a stolen code without its verifier."""
    # Given a valid browser authorization
    consent = authorize(client, user_factory()).json()
    payload = dict(
        grant_type="authorization_code",
        code=consent["code"],
        code_verifier=verifier,
        redirect_uri=REDIRECT,
        issuer=ISSUER,
    )
    # When the wrong proof is supplied
    response = post(client, "token", payload)
    # Then the code remains unconsumed for the legitimate app
    assert response.status_code == 400
    assert HealthSyncAuthorization.objects.get().consumed_at is None


@pytest.mark.django_db
def test_expired_authorization_and_inactive_owner_fail_closed(
    client, user_factory
):
    """Expired browser codes and disabled accounts cannot grant sync access."""
    # Given an authorization whose short handoff lifetime has elapsed
    user = user_factory()
    consent = authorize(client, user).json()
    HealthSyncAuthorization.objects.update(expires_at=timezone.now())
    payload = dict(
        grant_type="authorization_code",
        code=consent["code"],
        code_verifier=VERIFIER,
        redirect_uri=REDIRECT,
        issuer=ISSUER,
    )
    # When it is exchanged
    response = post(client, "token", payload)
    # Then it fails without creating a device
    assert response.status_code == 400
    assert not HealthSyncDevice.objects.exists()
    # And disabling the owner stops existing device access
    token, _ = HealthSyncDevice.issue(user, "Phone")
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert HealthSyncDevice.authenticate(token) is None


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["authorize", "token", "revoke"])
def test_auth_endpoints_are_rate_limited(client, user_factory, mocker, action):
    """Public credential requests are bounded before database lookups."""
    # Given exhausted client/global limits
    mocker.patch(
        "apps.health_sync.auth._pairing_rate_limited", return_value=True
    )
    user = user_factory()
    token = jwt.encode(
        {"sub": str(user.pk)}, settings.SECRET_KEY, algorithm="HS256"
    )
    # When another request arrives
    response = post(client, action, {}, HTTP_AUTHORIZATION=f"Bearer {token}")
    # Then it cannot perform authorization work
    assert response.status_code == 429


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action,payload",
    [
        ("token", []),
        ("token", {"issuer": "http://testserver"}),
        ("token", {"issuer": ISSUER}),
        ("revoke", {"issuer": ISSUER}),
        (
            "token",
            {
                "issuer": ISSUER,
                "grant_type": "refresh_token",
                "refresh_token": None,
            },
        ),
        (
            "token",
            {
                "issuer": ISSUER,
                "grant_type": "refresh_token",
                "refresh_token": "r" * 43,
                "next_refresh_token": "r" * 43,
            },
        ),
    ],
)
def test_invalid_token_requests_return_fixed_errors(client, action, payload):
    """Malformed public input never produces a successful grant."""
    # Given untrusted input without a usable credential
    # When it reaches a public credential endpoint
    response = post(client, action, payload)
    # Then failure does not reflect secrets or arbitrary input
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_grant"}


@pytest.mark.django_db
def test_authorization_requires_bearer_and_exact_browser_origin(
    client, user_factory
):
    """Cookie-only sessions and cross-site requests cannot grant device access."""
    # Given a logged-in Django cookie and no account bearer header
    user = user_factory()
    client.force_login(user)
    # When a browser tries cookie-only or invalid-bearer consent
    cookie = post(client, "authorize", {})
    invalid = post(client, "authorize", {}, HTTP_AUTHORIZATION="Bearer bad")
    token = jwt.encode(
        {"sub": str(user.pk)}, settings.SECRET_KEY, algorithm="HS256"
    )
    origin = post(
        client,
        "authorize",
        {"issuer": ISSUER},
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_ORIGIN="https://evil.example.com",
    )
    # Then explicit same-origin bearer authentication is required
    assert cookie.status_code == invalid.status_code == 401
    assert origin.status_code == 400
    assert not HealthSyncAuthorization.objects.exists()
