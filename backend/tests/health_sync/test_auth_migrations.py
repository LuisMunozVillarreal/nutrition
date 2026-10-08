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
