"""Command tests for Garmin activity sync."""

from __future__ import annotations

import io
import json

import pytest
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError

from apps.garmin.management.commands.sync_garmin import Command
from apps.garmin.models import GarminConnection

User = get_user_model()


def _create_user(email: str):
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


def _usable_connection(user):
    """Create an active row that passes the command's credential defense."""
    return GarminConnection.objects.create(
        user=user,
        access_token_encrypted="test-ciphertext",
    )


def test_sync_command_returns_summary_for_selected_user(monkeypatch):
    """Command should support user-id filtering.

    Emits per-connection JSON output.
    """
    _user_one = _create_user("command-one@example.com")
    _user_two = _create_user("command-two@example.com")

    _usable_connection(_user_one)
    _usable_connection(_user_two)

    def _fake_sync(connection):
        if connection.user_id == _user_one.id:
            return type(
                "Summary",
                (),
                {
                    "imported": 1,
                    "duplicates": 0,
                    "unsupported": 0,
                    "invalid": 0,
                },
            )
        if connection.user_id == _user_two.id:
            raise ValueError("blocked")
        raise AssertionError("unexpected")

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )

    output = io.StringIO()
    Command(stdout=output).handle(user_id=_user_one.id)
    rows = json.loads(output.getvalue())

    assert len(rows) == 1
    assert rows[0]["user_id"] == _user_one.id
    assert rows[0]["imported"] == 1


def test_sync_command_returns_errors_for_failing_connections(monkeypatch):
    """Emit errors per failing connection.

    Continue to process remaining connections.
    """
    user_one = _create_user("command-fail-one@example.com")
    user_two = _create_user("command-fail-two@example.com")

    _usable_connection(user_one)
    _usable_connection(user_two)

    def _fake_sync(connection):
        raise ValueError("boom")

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )

    output = io.StringIO()
    with pytest.raises(CommandError):
        Command(stdout=output).handle(user_id=None)
    rows = json.loads(output.getvalue())

    assert len(rows) == 2
    assert all("error" in row for row in rows)
    assert {row["error"] for row in rows} == {"sync_failed"}


def test_sync_command_reconciles_pending_rows_after_sync(monkeypatch):
    """Each synced connection should run pending reconciliation."""
    user = _create_user("command-reconcile@example.com")
    connection = _usable_connection(user)
    captured = {}

    def _fake_sync(_connection):
        return type(
            "Summary",
            (),
            {
                "imported": 1,
                "duplicates": 0,
                "unsupported": 0,
                "invalid": 0,
            },
        )

    def _fake_reconcile(reconcile_connection):
        captured["connection_id"] = reconcile_connection.pk
        return 1

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )
    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin."
        "reconcile_pending_garmin_activities",
        _fake_reconcile,
    )

    output = io.StringIO()
    Command(stdout=output).handle(user_id=user.id)

    rows = json.loads(output.getvalue())
    assert len(rows) == 1
    assert rows[0]["imported"] == 1
    assert rows[0].get("error") is None
    assert captured["connection_id"] == connection.pk


def test_sync_command_redacts_reconcile_errors(monkeypatch):
    """Reconcile failures are redacted to stable error codes."""
    user = _create_user("command-reconcile-failed@example.com")
    _usable_connection(user)

    def _fake_sync(_connection):
        return type(
            "Summary",
            (),
            {
                "imported": 1,
                "duplicates": 0,
                "unsupported": 0,
                "invalid": 0,
            },
        )

    def _fake_reconcile(_connection):
        raise ValueError("secret failure detail")

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )
    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin."
        "reconcile_pending_garmin_activities",
        _fake_reconcile,
    )

    output = io.StringIO()
    with pytest.raises(CommandError):
        Command(stdout=output).handle(user_id=user.id)

    rows = json.loads(output.getvalue())
    assert len(rows) == 1
    assert rows[0]["error"] == "reconcile_failed"
    assert rows[0]["reconciled"] == "error"


def test_sync_command_continues_to_reconcile_when_sync_fails(monkeypatch):
    """Reconciliation should run when sync fails for a connection."""
    user = _create_user("command-sync-failed-reconcile@example.com")
    connection = _usable_connection(user)
    captured = {}

    def _fake_sync(_connection):
        raise ValueError("sync down")

    def _fake_reconcile(reconcile_connection):
        captured["connection_id"] = reconcile_connection.pk
        return 1

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )
    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin."
        "reconcile_pending_garmin_activities",
        _fake_reconcile,
    )

    output = io.StringIO()
    with pytest.raises(CommandError):
        Command(stdout=output).handle(user_id=user.id)

    rows = json.loads(output.getvalue())
    assert len(rows) == 1
    assert rows[0]["error"] == "sync_failed"
    assert rows[0]["reconciled"] == "ok"
    assert captured["connection_id"] == connection.pk


def test_sync_command_with_no_active_connections_succeeds():
    """No active rows should report an empty result and exit successfully."""
    user = _create_user("command-no-active@example.com")
    GarminConnection.objects.create(
        user=user,
        status=GarminConnection.Status.DISCONNECTED,
    )

    output = io.StringIO()
    Command(stdout=output).handle(user_id=None)

    rows = json.loads(output.getvalue())
    assert rows == []


def test_sync_command_raises_on_mixed_success_and_failure(monkeypatch):
    """Failure in one path must make the command exit non-zero."""
    user_a = _create_user("command-mixed-success-a@example.com")
    user_b = _create_user("command-mixed-success-b@example.com")
    _usable_connection(user_a)
    _usable_connection(user_b)
    reconcile_calls: list[int] = []

    def _fake_sync(connection):
        if connection.user_id == user_a.id:
            return type(
                "Summary",
                (),
                {
                    "imported": 1,
                    "duplicates": 0,
                    "unsupported": 0,
                    "invalid": 0,
                },
            )
        raise ValueError("boom")

    def _fake_reconcile(reconcile_connection):
        reconcile_calls.append(reconcile_connection.pk)
        return 1

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )
    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin."
        "reconcile_pending_garmin_activities",
        _fake_reconcile,
    )

    output = io.StringIO()
    with pytest.raises(CommandError):
        Command(stdout=output).handle(user_id=None)

    rows = json.loads(output.getvalue())
    assert len(rows) == 2
    assert {row["error"] for row in rows if row.get("error") is not None} == {
        "sync_failed"
    }
    assert len(reconcile_calls) == 2


def test_sync_command_raises_when_all_connections_fail(monkeypatch):
    """Two failing connections should still report both and raise."""
    user_a = _create_user("command-all-fail-a@example.com")
    user_b = _create_user("command-all-fail-b@example.com")
    _usable_connection(user_a)
    _usable_connection(user_b)

    def _fake_sync(_connection):
        raise ValueError("boom")

    def _fake_reconcile(_reconcile_connection):
        return 1

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )
    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin."
        "reconcile_pending_garmin_activities",
        _fake_reconcile,
    )

    output = io.StringIO()
    with pytest.raises(CommandError):
        Command(stdout=output).handle(user_id=None)

    rows = json.loads(output.getvalue())
    assert len(rows) == 2
    assert all(row["error"] == "sync_failed" for row in rows)


def test_sync_command_ignores_inactive_connections(monkeypatch):
    """Inactive connections must be skipped from command batches."""
    user_active = _create_user("command-active@example.com")
    user_inactive = _create_user("command-inactive@example.com")
    active_connection = _usable_connection(user_active)
    GarminConnection.objects.create(
        user=user_inactive,
        status=GarminConnection.Status.DISCONNECTED,
    )
    calls: list[int] = []

    def _fake_sync(connection):
        calls.append(connection.pk)
        return type(
            "Summary",
            (),
            {
                "imported": 1,
                "duplicates": 0,
                "unsupported": 0,
                "invalid": 0,
            },
        )

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )

    output = io.StringIO()
    Command(stdout=output).handle(user_id=None)

    rows = json.loads(output.getvalue())
    assert len(rows) == 1
    assert rows[0]["connection_id"] == active_connection.pk
    assert calls == [active_connection.pk]


def test_sync_command_ignores_active_rows_without_usable_credentials(
    monkeypatch,
):
    """A defensive query filter skips active credentialless placeholders."""
    user = _create_user("command-credentialless@example.com")
    GarminConnection.objects.create(
        user=user,
        status=GarminConnection.Status.ACTIVE,
    )
    calls: list[int] = []
    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        lambda connection: calls.append(connection.pk),
    )

    output = io.StringIO()
    Command(stdout=output).handle(user_id=None)

    assert json.loads(output.getvalue()) == []
    assert calls == []
