"""Credential recovery and compromise regressions for browser grants."""

import pytest
from django.core.cache import cache
from django.db import connection

from apps.health_sync.auth import _spent_digest
from apps.health_sync.models import (
    HealthSyncDevice,
    HealthSyncGrant,
    HealthSyncSpentRefresh,
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


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("generations", [2, 4])
@pytest.mark.parametrize("successor", ["b", "z"])
def test_older_spent_refresh_revokes_only_its_family(
    client, user_factory, settings, generations, successor
):
    """Every consumed generation detects reuse, even its obsolete exact retry."""
    settings.HEALTH_SYNC_TOKEN_PEPPER = "old-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    tokens = credentials(client, user_factory())
    unrelated = credentials(client, user_factory())
    current = tokens["refresh_token"]
    for index in range(generations):
        replacement = chr(ord("b") + index) * 43
        response = rotate(client, current, replacement)
        assert response.status_code == 200
        assert rotate(client, current, replacement).json() == response.json()
        current = replacement
        settings.HEALTH_SYNC_TOKEN_PEPPER = "new-test-pepper"
        settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = ["old-test-pepper"]

    rejected = rotate(client, tokens["refresh_token"], successor * 43)

    assert rejected.status_code == 400
    assert (
        HealthSyncDevice.authenticate(response.json()["access_token"]) is None
    )
    assert rotate(client, current, "y" * 43).status_code == 400
    assert (
        HealthSyncDevice.objects.filter(revoked_at__isnull=False).count() == 1
    )
    assert HealthSyncDevice.authenticate(unrelated["access_token"])
    assert (
        rotate(client, unrelated["refresh_token"], "x" * 43).status_code == 200
    )


@pytest.mark.django_db(transaction=True)
def test_spent_recognition_survives_retiring_a_pepper(
    client, user_factory, settings
):
    """A migrated live family cannot hide older reuse by retiring its pepper."""
    settings.HEALTH_SYNC_TOKEN_PEPPER = "old-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    tokens = credentials(client, user_factory())
    assert rotate(client, tokens["refresh_token"], "b" * 43).status_code == 200
    settings.HEALTH_SYNC_TOKEN_PEPPER = "new-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = ["old-test-pepper"]
    winner = rotate(client, "b" * 43, "c" * 43)
    assert winner.status_code == 200
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []

    assert rotate(client, tokens["refresh_token"], "z" * 43).status_code == 400
    assert HealthSyncDevice.authenticate(winner.json()["access_token"]) is None
    assert rotate(client, "c" * 43, "d" * 43).status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("replacement", ["original", "previous"])
def test_rotation_cannot_reactivate_a_spent_refresh(
    client, user_factory, replacement
):
    """Client-selected successors cannot make a consumed credential current."""
    tokens = credentials(client, user_factory())
    first = rotate(client, tokens["refresh_token"], "b" * 43)
    assert first.status_code == 200
    second = rotate(client, "b" * 43, "c" * 43)
    assert second.status_code == 200

    successor = (
        tokens["refresh_token"] if replacement == "original" else "b" * 43
    )
    rejected = rotate(client, "c" * 43, successor)

    assert rejected.status_code == 400
    assert HealthSyncDevice.authenticate(second.json()["access_token"])
    assert rotate(client, "c" * 43, "d" * 43).status_code == 200


@pytest.mark.django_db
def test_spent_history_is_atomic_and_retained_from_legacy_grants(
    client, user_factory, monkeypatch
):
    """Failure rolls back history; an existing predecessor survives upgrades."""
    tokens = credentials(client, user_factory())
    original_save = HealthSyncGrant.save

    def fail_save(*_args, **_kwargs):
        raise ValueError("Injected persistence failure")

    monkeypatch.setattr(HealthSyncGrant, "save", fail_save)
    assert rotate(client, tokens["refresh_token"], "b" * 43).status_code == 400
    assert not HealthSyncSpentRefresh.objects.exists()
    assert HealthSyncGrant.objects.get().refresh_hash == _token_digest(
        tokens["refresh_token"]
    )
    assert HealthSyncDevice.authenticate(tokens["access_token"])

    monkeypatch.setattr(HealthSyncGrant, "save", original_save)
    assert rotate(client, tokens["refresh_token"], "b" * 43).status_code == 200
    # Emulate the populated predecessor-only state from migration 0005.
    HealthSyncSpentRefresh.objects.all().delete()
    assert rotate(client, "b" * 43, "c" * 43).status_code == 200
    assert set(
        HealthSyncSpentRefresh.objects.values_list("token_hash", flat=True)
    ) == {
        _token_digest(tokens["refresh_token"]),
        _spent_digest("b" * 43),
    }
    assert rotate(client, tokens["refresh_token"], "z" * 43).status_code == 400
    assert HealthSyncDevice.objects.get().revoked_at is not None
    HealthSyncDevice.objects.get().delete()
    assert not HealthSyncSpentRefresh.objects.exists()


@pytest.mark.django_db
def test_unknown_or_wrong_issuer_refresh_does_not_revoke_family(
    client, user_factory, settings
):
    """Only an issuer-bound known credential may revoke its own device family."""
    settings.ALLOWED_HOSTS = ["testserver", "other.example.com"]
    tokens = credentials(client, user_factory())
    assert rotate(client, tokens["refresh_token"], "b" * 43).status_code == 200
    winner = rotate(client, "b" * 43, "c" * 43)
    assert winner.status_code == 200
    assert rotate(client, "u" * 43, "v" * 43).status_code == 400
    rejected = post(
        client,
        "token",
        {
            "issuer": "https://other.example.com",
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "next_refresh_token": "z" * 43,
        },
        HTTP_HOST="other.example.com",
    )
    assert rejected.status_code == 400
    assert HealthSyncDevice.objects.get().revoked_at is None
    assert HealthSyncDevice.authenticate(winner.json()["access_token"])


@pytest.mark.django_db
def test_stale_authentication_rehash_revalidates_the_access_hash(
    client, user_factory, settings
):
    """An interleaved refresh must survive a stale write on every backend."""
    settings.HEALTH_SYNC_TOKEN_PEPPER = "old-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    tokens = credentials(client, user_factory())
    settings.HEALTH_SYNC_TOKEN_PEPPER = "new-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = ["old-test-pepper"]
    winner = []

    def checkpoint(execute, sql, params, many, context):
        if not winner and sql.startswith(
            'UPDATE "health_sync_healthsyncdevice"'
        ):
            winner.append(None)
            response = rotate(client, tokens["refresh_token"], "b" * 43)
            assert response.status_code == 200
            winner[0] = response.json()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(checkpoint):
        assert HealthSyncDevice.authenticate(tokens["access_token"]) is None
    assert HealthSyncDevice.authenticate(winner[0]["access_token"])


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
