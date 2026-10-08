"""Credential recovery and compromise regressions for browser grants."""

import pytest
from django.core.cache import cache

from apps.health_sync.models import (
    HealthSyncDevice,
    HealthSyncGrant,
    _token_digest,
)
from tests.health_sync.test_browser_auth import (
    ISSUER,
    REDIRECT,
    VERIFIER,
    authorize,
    post,
)


@pytest.fixture(autouse=True)
def reset_limits():
    """Isolate real endpoint rate counters for each regression."""
    cache.clear()


def credentials(client, user):
    """Issue a real browser grant through the public endpoint."""
    consent = authorize(client, user).json()
    return post(
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


def rotate(client, old, new):
    """Submit a durable replacement to the public token endpoint."""
    return post(
        client,
        "token",
        {
            "issuer": ISSUER,
            "grant_type": "refresh_token",
            "refresh_token": old,
            "next_refresh_token": new,
        },
    )


@pytest.mark.django_db(transaction=True)
def test_divergent_spent_refresh_revokes_the_winning_family(
    client, user_factory
):
    """A detected stolen refresh cannot keep its winning replacement alive."""
    tokens = credentials(client, user_factory())
    winner = rotate(client, tokens["refresh_token"], "b" * 43).json()
    assert rotate(client, tokens["refresh_token"], "b" * 43).json() == winner

    rejected = rotate(client, tokens["refresh_token"], "c" * 43)

    assert rejected.status_code == 400
    assert HealthSyncDevice.objects.get().revoked_at is not None
    assert HealthSyncDevice.authenticate(winner["access_token"]) is None
    assert rotate(client, "b" * 43, "d" * 43).status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["refresh", "retry", "revoke"])
def test_pepper_rotation_preserves_renewal_and_revocation(
    client, user_factory, settings, operation
):
    """Fallbacks keep durable grants usable while real rotations migrate them."""
    settings.HEALTH_SYNC_TOKEN_PEPPER = "old-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    tokens = credentials(client, user_factory())
    if operation == "retry":
        winner = rotate(client, tokens["refresh_token"], "b" * 43).json()
    settings.HEALTH_SYNC_TOKEN_PEPPER = "new-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = ["old-test-pepper"]

    if operation == "revoke":
        response = post(
            client,
            "revoke",
            {"issuer": ISSUER, "refresh_token": tokens["refresh_token"]},
        )
        assert response.status_code == 200
        assert HealthSyncDevice.authenticate(tokens["access_token"]) is None
    else:
        response = rotate(client, tokens["refresh_token"], "b" * 43)
        assert response.status_code == 200
        if operation == "retry":
            assert response.json() == winner
            # Authentication rehashes access independently of refresh metadata.
            assert HealthSyncDevice.authenticate(winner["access_token"])
            assert (
                rotate(client, tokens["refresh_token"], "b" * 43).json()
                == winner
            )
        assert HealthSyncDevice.authenticate(response.json()["access_token"])
        migrated = rotate(client, "b" * 43, "c" * 43)
        assert migrated.status_code == 200
        grant = HealthSyncGrant.objects.get()
        assert grant.refresh_hash == _token_digest("c" * 43)
        assert grant.previous_refresh_hash == _token_digest("b" * 43)
        settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
        assert rotate(client, "b" * 43, "c" * 43).json() == migrated.json()
        assert HealthSyncDevice.authenticate(migrated.json()["access_token"])
