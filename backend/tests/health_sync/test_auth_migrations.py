"""Forward compatibility for the spent-refresh history expansion."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.health_sync.auth import _spent_digest
from apps.health_sync.models import HealthSyncGrant, HealthSyncSpentRefresh
from tests.health_sync.test_auth_recovery import credentials, rotate

OLD_TARGET = ("health_sync", "0005_healthsyncauthorization_healthsyncgrant")
NEW_TARGET = ("health_sync", "0006_healthsyncspentrefresh")


@pytest.mark.django_db(transaction=True)
def test_spent_history_migration_preserves_populated_grants(
    client, user_factory
):
    """Expand existing grants without rewriting credentials or duplicating history."""
    tokens = credentials(client, user_factory())
    grant = HealthSyncGrant.objects.get()
    try:
        MigrationExecutor(connection).migrate([OLD_TARGET])
        executor = MigrationExecutor(connection)
        historical = executor.loader.project_state([OLD_TARGET]).apps
        old_grants = historical.get_model("health_sync", "HealthSyncGrant")
        before = old_grants.objects.values().get(pk=grant.pk)
        executor.migrate([NEW_TARGET])
        assert HealthSyncGrant.objects.values().get(pk=grant.pk) == before
        assert not HealthSyncSpentRefresh.objects.exists()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        response = rotate(client, tokens["refresh_token"], "b" * 43)
        assert response.status_code == 200
        fingerprint = _spent_digest(tokens["refresh_token"])
        assert HealthSyncSpentRefresh.objects.filter(
            grant=grant, token_hash=fingerprint
        ).exists()
        with pytest.raises(IntegrityError), transaction.atomic():
            HealthSyncSpentRefresh.objects.create(
                grant=grant, token_hash=fingerprint
            )
        assert (
            rotate(client, tokens["refresh_token"], "b" * 43).json()
            == response.json()
        )
        assert HealthSyncSpentRefresh.objects.count() == 1
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_claim_migration_preserves_ambiguous_history_without_logout(
    client, user_factory
):
    """Expand populated 0006 without inventing missing fingerprints or owners."""
    from apps.health_sync.models import (
        HealthSyncDevice,
        HealthSyncRefreshClaim,
    )

    first = credentials(client, user_factory())
    second = credentials(client, user_factory())
    unrelated = credentials(client, user_factory())
    assert rotate(client, first["refresh_token"], "b" * 43).status_code == 200
    winner = rotate(client, "b" * 43, "c" * 43).json()
    try:
        MigrationExecutor(connection).migrate([NEW_TARGET])
        executor = MigrationExecutor(connection)
        historical = executor.loader.project_state([NEW_TARGET]).apps
        grants = historical.get_model("health_sync", "HealthSyncGrant")
        spent = historical.get_model("health_sync", "HealthSyncSpentRefresh")
        devices = historical.get_model("health_sync", "HealthSyncDevice")
        first_grant, second_grant, _other = list(grants.objects.order_by("pk"))
        grants.objects.filter(pk=second_grant.pk).update(
            refresh_hash=first_grant.previous_refresh_hash
        )
        spent.objects.create(
            grant_id=second_grant.pk,
            token_hash=_spent_digest(first["refresh_token"]),
        )
        before = [
            list(model.objects.order_by("pk").values())
            for model in (grants, spent, devices)
        ]
        executor.migrate([("health_sync", "0007_healthsyncrefreshclaim")])
        assert [
            list(model.objects.order_by("pk").values())
            for model in (grants, spent, devices)
        ] == before
        assert not HealthSyncRefreshClaim.objects.exists()
        assert not HealthSyncDevice.objects.filter(
            revoked_at__isnull=False
        ).exists()
        assert (
            rotate(client, unrelated["refresh_token"], "b" * 43).status_code
            == 400
        )
        assert (
            rotate(client, unrelated["refresh_token"], "x" * 43).status_code
            == 200
        )
        assert (
            rotate(client, first["refresh_token"], "z" * 43).status_code == 400
        )
        assert HealthSyncDevice.authenticate(winner["access_token"]) is None
        assert HealthSyncDevice.authenticate(second["access_token"]) is None
        assert HealthSyncRefreshClaim.objects.count() == 1
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
