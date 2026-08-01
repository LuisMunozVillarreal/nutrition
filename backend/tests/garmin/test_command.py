"""Command tests for Garmin activity sync."""

from __future__ import annotations

import io
import json

from django.contrib.auth import get_user_model

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


def test_sync_command_returns_summary_for_selected_user(monkeypatch):
    """Command should support user-id filtering.

    Emits per-connection JSON output.
    """
    _user_one = _create_user("command-one@example.com")
    _user_two = _create_user("command-two@example.com")

    GarminConnection.objects.create(user=_user_one)
    GarminConnection.objects.create(user=_user_two)

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

    GarminConnection.objects.create(user=user_one)
    GarminConnection.objects.create(user=user_two)

    def _fake_sync(connection):
        raise ValueError("boom")

    monkeypatch.setattr(
        "apps.garmin.management.commands.sync_garmin.sync_connection",
        _fake_sync,
    )

    output = io.StringIO()
    Command(stdout=output).handle(user_id=None)
    rows = json.loads(output.getvalue())

    assert len(rows) == 2
    assert all("error" in row for row in rows)
    assert {row["error"] for row in rows} == {"sync_failed"}


def test_sync_command_reconciles_pending_rows_after_sync(monkeypatch):
    """Each synced connection should run pending reconciliation."""
    user = _create_user("command-reconcile@example.com")
    connection = GarminConnection.objects.create(user=user)
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
    GarminConnection.objects.create(user=user)

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
    Command(stdout=output).handle(user_id=user.id)

    rows = json.loads(output.getvalue())
    assert len(rows) == 1
    assert rows[0]["error"] == "reconcile_failed"
    assert rows[0]["reconciled"] == "error"
