"""Cross-family renewal ownership regressions through the public endpoints."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.cache import cache
from django.db import IntegrityError, connection, connections, transaction
from django.db.models.query import QuerySet
from django.test import Client

from apps.health_sync.auth import _spent_digest
from apps.health_sync.models import (
    HealthSyncDevice,
    HealthSyncGrant,
    HealthSyncRefreshClaim,
    _token_digest,
)
from apps.users.models import User
from tests.health_sync.test_auth_recovery import credentials, rotate
from tests.health_sync.test_browser_auth import (
    ISSUER,
    REDIRECT,
    VERIFIER,
    authorize,
    post,
)


@pytest.fixture(autouse=True)
def reset_limits():
    """Keep synthetic request counters independent."""
    cache.clear()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("generation", [0, 1, 2])
def test_another_family_cannot_claim_a_known_refresh(
    client, user_factory, generation
):
    """Current, predecessor and older credentials remain owned by their family."""
    victim = credentials(client, user_factory())
    other = credentials(client, user_factory())
    current = victim["refresh_token"]
    winner = victim
    for replacement in ["b" * 43, "c" * 43][:generation]:
        response = rotate(client, current, replacement)
        assert response.status_code == 200
        winner = response.json()
        current = replacement

    rejected = rotate(client, other["refresh_token"], victim["refresh_token"])

    assert rejected.status_code == 400
    assert HealthSyncDevice.authenticate(other["access_token"])
    assert HealthSyncDevice.authenticate(winner["access_token"])
    assert rotate(client, other["refresh_token"], "x" * 43).status_code == 200
    if generation:
        assert (
            rotate(client, victim["refresh_token"], "z" * 43).status_code
            == 400
        )
        assert HealthSyncDevice.authenticate(winner["access_token"]) is None
        assert rotate(client, current, "y" * 43).status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["refresh", "revoke"])
@pytest.mark.parametrize("inactive_owner", [False, True])
def test_existing_ambiguous_refresh_revokes_all_matching_families(
    client, user_factory, monkeypatch, inactive_owner, operation
):
    """A pre-upgrade shadow cannot suppress durable compromise revocation."""
    victim = credentials(client, user_factory())
    other = credentials(client, user_factory())
    unrelated = credentials(client, user_factory())
    assert rotate(client, victim["refresh_token"], "b" * 43).status_code == 200
    winner = rotate(client, "b" * 43, "c" * 43).json()
    HealthSyncGrant.objects.filter(
        refresh_hash=_token_digest(other["refresh_token"])
    ).update(refresh_hash=_token_digest(victim["refresh_token"]))

    if inactive_owner:
        User.objects.filter(
            health_sync_devices__token_hash=_token_digest(
                other["access_token"]
            )
        ).update(is_active=False)
    acquired = []
    original = QuerySet._fetch_all

    def fetch(queryset):
        if queryset.query.select_for_update and queryset._result_cache is None:
            acquired.append((queryset.model, queryset.query.order_by))
        return original(queryset)

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    if operation == "refresh":
        response = rotate(client, victim["refresh_token"], "z" * 43)
    else:
        response = post(
            client,
            "revoke",
            {"issuer": ISSUER, "refresh_token": victim["refresh_token"]},
        )
    assert acquired == [
        (User, ("pk",)),
        (HealthSyncDevice, ("pk",)),
        (HealthSyncGrant, ("pk",)),
    ]

    assert response.status_code == 400
    assert HealthSyncDevice.authenticate(winner["access_token"]) is None
    assert HealthSyncDevice.authenticate(other["access_token"]) is None
    assert HealthSyncDevice.authenticate(unrelated["access_token"])
    assert rotate(client, "c" * 43, "d" * 43).status_code == 400
    assert (
        HealthSyncDevice.objects.filter(revoked_at__isnull=False).count() == 2
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("advance_winner", [False, True])
def test_concurrent_families_cannot_claim_the_same_successor(
    client, user_factory, monkeypatch, advance_winner
):
    """A database backstop arbitrates after both prechecks see an unused token."""
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL concurrency required")
    tokens = [credentials(client, user_factory()) for _ in range(2)]
    barrier = threading.Barrier(2)
    completed = threading.Event()
    local = threading.local()
    pids = []
    original = QuerySet.exists

    def exists(queryset):
        result = original(queryset)
        if queryset.model is HealthSyncGrant:
            _sql, params = queryset.query.sql_with_params()
            if _token_digest("s" * 43) in params:
                assert not result
                barrier.wait(timeout=8)
                if advance_winner and local.index == 1:
                    assert completed.wait(8)
        return result

    def claim(item):
        index, token = item
        local.index = index
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '8s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.append(cursor.fetchone()[0])
            response = rotate(Client(), token["refresh_token"], "s" * 43)
            if advance_winner and index == 0:
                assert response.status_code == 200
                assert rotate(Client(), "s" * 43, "u" * 43).status_code == 200
                response = rotate(Client(), "u" * 43, "v" * 43)
            return response.status_code, response.json()
        finally:
            if index == 0:
                completed.set()
            connections.close_all()

    monkeypatch.setattr(QuerySet, "exists", exists)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, enumerate(tokens)))
    monkeypatch.setattr(QuerySet, "exists", original)
    assert len(set(pids)) == 2
    assert sorted(status for status, _body in results) == [200, 400]
    for token, (status, body) in zip(tokens, results):
        if status == 200:
            assert HealthSyncDevice.authenticate(body["access_token"])
            assert (
                rotate(
                    client,
                    "u" * 43 if advance_winner else token["refresh_token"],
                    "v" * 43 if advance_winner else "s" * 43,
                ).json()
                == body
            )
        else:
            assert HealthSyncDevice.authenticate(token["access_token"])
            assert (
                rotate(client, token["refresh_token"], "t" * 43).status_code
                == 200
            )


@pytest.mark.django_db
def test_claims_are_unique_atomic_and_retained_after_pepper_retirement(
    client, user_factory, settings, monkeypatch
):
    """Claims survive rotation and rollback without authorizing retired hashes."""
    settings.HEALTH_SYNC_TOKEN_PEPPER = "synthetic-old-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    tokens = credentials(client, user_factory())
    other = credentials(client, user_factory())
    device = HealthSyncDevice.objects.get(
        token_hash=_token_digest(tokens["access_token"])
    )
    fingerprint = _spent_digest(tokens["refresh_token"])
    assert (
        HealthSyncRefreshClaim.objects.get(fingerprint=fingerprint).device
        == device
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        HealthSyncRefreshClaim.objects.create(
            device=device, fingerprint=fingerprint
        )

    original = HealthSyncGrant.save

    def fail_save(*_args, **_kwargs):
        raise ValueError("Synthetic persistence failure")

    monkeypatch.setattr(HealthSyncGrant, "save", fail_save)
    assert rotate(client, tokens["refresh_token"], "b" * 43).status_code == 400
    assert not HealthSyncRefreshClaim.objects.filter(
        fingerprint=_spent_digest("b" * 43)
    ).exists()
    monkeypatch.setattr(HealthSyncGrant, "save", original)
    settings.HEALTH_SYNC_TOKEN_PEPPER = "synthetic-new-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = ["synthetic-old-pepper"]
    assert rotate(client, other["refresh_token"], "c" * 43).status_code == 200
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    assert rotate(client, "c" * 43, tokens["refresh_token"]).status_code == 400
    assert rotate(client, tokens["refresh_token"], "d" * 43).status_code == 400
    device.refresh_from_db()
    assert device.revoked_at is not None
    device.delete()
    assert not HealthSyncRefreshClaim.objects.filter(
        fingerprint=fingerprint
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("generation", [0, 2])
def test_exchange_cannot_issue_another_familys_refresh(
    client, user_factory, monkeypatch, generation
):
    """A collision rolls back code consumption and the newly issued device."""
    tokens = credentials(client, user_factory())
    old = tokens["refresh_token"]
    for successor in ["b" * 43, "c" * 43][:generation]:
        assert rotate(client, old, successor).status_code == 200
        old = successor
    code = authorize(client, user_factory()).json()["code"]
    values = iter(["a" * 43, tokens["refresh_token"]])
    monkeypatch.setattr(
        "apps.health_sync.auth.secrets.token_urlsafe",
        lambda _size: next(values),
    )
    before = HealthSyncDevice.objects.count()
    response = post(
        client,
        "token",
        {
            "issuer": ISSUER,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": VERIFIER,
            "redirect_uri": REDIRECT,
        },
    )
    assert response.status_code == 400
    assert HealthSyncDevice.objects.count() == before
    from apps.health_sync.models import (
        HealthSyncAuthorization,
        _pairing_digest,
    )

    assert (
        HealthSyncAuthorization.objects.get(
            code_hash=_pairing_digest(code)
        ).consumed_at
        is None
    )


@pytest.mark.django_db
def test_late_claim_conflict_preserves_outer_transaction(
    client, user_factory, monkeypatch
):
    """A late unique collision rolls back only the losing credential rotation."""
    loser = credentials(client, user_factory())
    winner = credentials(client, user_factory())
    original = QuerySet.exists
    interleaved = []

    def exists(queryset):
        result = original(queryset)
        if queryset.model is HealthSyncGrant and not interleaved:
            _sql, params = queryset.query.sql_with_params()
            if _token_digest("s" * 43) in params:
                assert not result
                interleaved.append(True)
                assert (
                    rotate(
                        client, winner["refresh_token"], "s" * 43
                    ).status_code
                    == 200
                )
                assert rotate(client, "s" * 43, "u" * 43).status_code == 200
                assert rotate(client, "u" * 43, "v" * 43).status_code == 200
        return result

    monkeypatch.setattr(QuerySet, "exists", exists)
    with transaction.atomic():
        response = rotate(client, loser["refresh_token"], "s" * 43)
        assert interleaved == [True]
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_grant"}
        assert not connection.needs_rollback
        assert HealthSyncDevice.authenticate(loser["access_token"])
        assert (
            HealthSyncGrant.objects.get(
                refresh_hash=_token_digest(loser["refresh_token"])
            ).previous_refresh_hash
            == ""
        )
    # The same-connection schedule rolls the injected winner back with the
    # losing rotation. The separate-connection test checks winner durability.
    assert HealthSyncDevice.authenticate(winner["access_token"])
    assert rotate(client, loser["refresh_token"], "t" * 43).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("generations", [1, 3])
def test_revoke_rejects_unambiguous_spent_credential(
    client, user_factory, generations
):
    """Historical ownership alone must not authorize the current-only revoke API."""
    tokens = credentials(client, user_factory())
    current = tokens["refresh_token"]
    for successor in ["b" * 43, "c" * 43, "d" * 43][:generations]:
        response = rotate(client, current, successor)
        assert response.status_code == 200
        current = successor

    rejected = post(
        client,
        "revoke",
        {"issuer": ISSUER, "refresh_token": tokens["refresh_token"]},
    )
    assert rejected.status_code == 400
    assert rejected.json() == {"error": "invalid_grant"}
    assert HealthSyncDevice.objects.get().revoked_at is None
    assert HealthSyncDevice.authenticate(response.json()["access_token"])
    assert rotate(client, current, "x" * 43).status_code == 200
