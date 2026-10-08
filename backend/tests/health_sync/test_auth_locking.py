"""Lock ordering for consent, exchange, and renewal."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.cache import cache
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import Client

from apps.health_sync.models import HealthSyncAuthorization, HealthSyncDevice
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
    """Isolate real endpoint rate counters for each regression."""
    cache.clear()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["exchange", "refresh"])
def test_credential_writers_lock_user_before_children(
    client, user_factory, monkeypatch, operation
):
    """A joined child query must not acquire the owner lock in reverse order."""
    user = user_factory()
    tokens = credentials(client, user) if operation == "refresh" else None
    code = authorize(client, user).json()["code"]
    acquired = []
    original = QuerySet._fetch_all

    def fetch(queryset):
        if queryset.query.select_for_update and queryset._result_cache is None:
            acquired.append(queryset.model)
        return original(queryset)

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    if operation == "exchange":
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
        child = HealthSyncAuthorization
    else:
        response = rotate(client, tokens["refresh_token"], "b" * 43)
        child = HealthSyncDevice

    assert response.status_code == 200
    assert acquired[0] is User
    assert child in acquired[1:]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["refresh", "revoke", "rehash"])
def test_access_rehash_cannot_overwrite_concurrent_credentials(
    client, user_factory, settings, operation
):
    """Pause a real connection's stale write while another changes the device."""
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL concurrency required")
    settings.HEALTH_SYNC_TOKEN_PEPPER = "old-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = []
    tokens = credentials(client, user_factory())
    unrelated = credentials(client, user_factory())
    settings.HEALTH_SYNC_TOKEN_PEPPER = "new-test-pepper"
    settings.HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS = ["old-test-pepper"]
    selected = threading.Event()
    resume = threading.Event()
    authentication_pid = []

    def authenticate():
        def checkpoint(execute, sql, params, many, context):
            if sql.startswith('UPDATE "health_sync_healthsyncdevice"'):
                selected.set()
                assert resume.wait(10)
            return execute(sql, params, many, context)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '8s'")
                cursor.execute("SELECT pg_backend_pid()")
                authentication_pid.append(cursor.fetchone()[0])
            with connection.execute_wrapper(checkpoint):
                return HealthSyncDevice.authenticate(tokens["access_token"])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(authenticate)
        try:
            assert selected.wait(5)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                assert authentication_pid != [cursor.fetchone()[0]]
            if operation == "refresh":
                winner = rotate(client, tokens["refresh_token"], "b" * 43)
                assert winner.status_code == 200
            elif operation == "revoke":
                response = post(
                    client,
                    "revoke",
                    {
                        "issuer": ISSUER,
                        "refresh_token": tokens["refresh_token"],
                    },
                )
                assert response.status_code == 200
            else:
                assert HealthSyncDevice.authenticate(tokens["access_token"])
        finally:
            resume.set()
        result = future.result(timeout=10)

    if operation == "refresh":
        assert HealthSyncDevice.authenticate(winner.json()["access_token"])
        assert result is None
        assert HealthSyncDevice.authenticate(tokens["access_token"]) is None
        assert (
            rotate(client, tokens["refresh_token"], "b" * 43).json()
            == winner.json()
        )
    elif operation == "revoke":
        assert result is None
        assert HealthSyncDevice.authenticate(tokens["access_token"]) is None
    else:
        assert result is not None
        assert HealthSyncDevice.authenticate(tokens["access_token"])
    assert HealthSyncDevice.authenticate(unrelated["access_token"])


@pytest.mark.django_db(transaction=True)
def test_consent_and_exchange_serialize_on_postgresql(client, user_factory):
    """Hold consent's owner lock until exchange blocks on another connection."""
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row locks required")
    user = user_factory()
    code = authorize(client, user).json()["code"]
    owner_locked = threading.Event()
    release_consent = threading.Event()
    exchange_started = threading.Event()
    exchange_pid = []

    def consent():
        def checkpoint(execute, sql, params, many, context):
            result = execute(sql, params, many, context)
            if 'FROM "users_user"' in sql and "FOR UPDATE" in sql:
                owner_locked.set()
                assert release_consent.wait(10)
            return result

        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '8s'")
            with connection.execute_wrapper(checkpoint):
                return authorize(Client(), user).status_code
        finally:
            connections.close_all()

    def exchange():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '8s'")
                cursor.execute("SELECT pg_backend_pid()")
                exchange_pid.append(cursor.fetchone()[0])
            exchange_started.set()
            return post(
                Client(),
                "token",
                {
                    "issuer": ISSUER,
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": VERIFIER,
                    "redirect_uri": REDIRECT,
                },
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        consent_future = pool.submit(consent)
        try:
            assert owner_locked.wait(5)
            exchange_future = pool.submit(exchange)
            assert exchange_started.wait(5)
            deadline = time.monotonic() + 5
            blocked = False
            while time.monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", exchange_pid)
                    blocked = bool(cursor.fetchone()[0])
                if blocked:
                    break
                time.sleep(0.01)
            assert blocked, "Exchange never waited on the consent connection"
        finally:
            release_consent.set()
        assert consent_future.result(timeout=10) == 201
        assert exchange_future.result(timeout=10) == 400
    assert not HealthSyncDevice.objects.exists()
