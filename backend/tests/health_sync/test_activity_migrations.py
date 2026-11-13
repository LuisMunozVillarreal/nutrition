"""Nullable activity metadata expansion on populated historical data."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.health_sync.models import ActivityImport, HealthSyncDevice


@pytest.mark.django_db(transaction=True)
def test_activity_metadata_migrations_preserve_rows_and_tombstones(
    user_factory, day_factory
):
    """Preserve source versions and user intent without guessing missing instants."""
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    _token, device = HealthSyncDevice.issue(user, "Phone")
    exercise = Exercise.objects.create(day=day, type="run", kcals=300)
    old = ("health_sync", "0008_merge_activity_and_browser_auth")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([old])
        historical = executor.loader.project_state([old]).apps
        imports = historical.get_model("health_sync", "ActivityImport")
        imports.objects.create(
            user_id=user.pk,
            device_id=device.pk,
            exercise_id=exercise.pk,
            source_record_id="active",
            source_modified_at=timezone.now(),
        )
        imports.objects.create(
            user_id=user.pk,
            device_id=device.pk,
            exercise_id=None,
            source_record_id="deleted",
            source_modified_at=timezone.now(),
            is_active=False,
        )
        before = list(imports.objects.order_by("pk").values())
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        after = list(ActivityImport.objects.order_by("pk").values())
        for previous, expanded in zip(before, after, strict=True):
            assert {key: expanded[key] for key in previous} == previous
            assert expanded["observed_at"] is None
            assert expanded["start_time"] is None
            assert expanded["end_time"] is None
        assert Exercise.objects.get(pk=exercise.pk).kcals == 300
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
