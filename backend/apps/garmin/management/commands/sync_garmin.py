"""Management command for Garmin activity synchronization."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, router

from apps.garmin.models import GarminConnection
from apps.garmin.services import (
    reconcile_pending_garmin_activities,
    sync_connection,
)


class Command(BaseCommand):
    """Run Garmin sync for one or all active connections."""

    help = "Synchronize Garmin activities for one or all connected users."

    def add_arguments(self, parser):  # type: ignore[override]
        """Register the optional user filter."""
        parser.add_argument(
            "--user-id",
            type=int,
            dest="user_id",
            required=False,
            help="Optional user id to sync only one Garmin connection.",
        )

    def handle(self, *args, **options):  # type: ignore[override]
        """Synchronize selected connections and emit a redacted summary."""
        user_id = options.get("user_id")
        using = router.db_for_write(GarminConnection)
        queryset = GarminConnection.objects.using(using).all()
        if user_id is not None:
            queryset = queryset.filter(user_id=user_id)
        queryset = queryset.filter(status=GarminConnection.Status.ACTIVE)

        failures = 0

        outcomes = []
        for connection in queryset.order_by("pk"):
            failure_row = {
                "connection_id": connection.pk,
                "user_id": connection.user_id,
                "reconciled": "not_attempted",
            }
            status_error = None
            try:
                summary = sync_connection(connection)
                failure_row.update(
                    {
                        "imported": summary.imported,
                        "duplicates": summary.duplicates,
                        "unsupported": summary.unsupported,
                        "invalid": summary.invalid,
                    }
                )
            except ValueError:
                status_error = "sync_failed"
            except OperationalError:
                status_error = "database_error"

            if status_error is not None:
                failure_row["error"] = status_error
                failures += 1

            try:
                reconcile_pending_garmin_activities(connection)
                failure_row["reconciled"] = "ok"
            except ValueError:
                failures += 1
                failure_row["reconciled"] = "error"
                if failure_row.get("error") is None:
                    failure_row["error"] = "reconcile_failed"
            except OperationalError:
                failures += 1
                failure_row["reconciled"] = "error"
                if failure_row.get("error") is None:
                    failure_row["error"] = "database_error"

            outcomes.append(failure_row)

        if failures:
            self.stdout.write(json.dumps(outcomes, sort_keys=True))
            raise CommandError("Garmin sync finished with failures")
        self.stdout.write(json.dumps(outcomes, sort_keys=True))
