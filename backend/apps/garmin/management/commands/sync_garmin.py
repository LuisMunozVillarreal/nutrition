"""Management command for Garmin activity synchronization."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
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

        outcomes = []
        for connection in queryset.order_by("pk"):
            status_error = None
            try:
                summary = sync_connection(connection)
                outcomes.append(
                    {
                        "connection_id": connection.pk,
                        "user_id": connection.user_id,
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
                outcomes.append(
                    {
                        "connection_id": connection.pk,
                        "user_id": connection.user_id,
                        "error": status_error,
                    }
                )
                continue

            try:
                reconcile_pending_garmin_activities(connection)
            except ValueError:
                outcomes[-1]["reconciled"] = "error"
                outcomes[-1]["error"] = "reconcile_failed"
            except OperationalError:
                outcomes[-1]["reconciled"] = "error"
                outcomes[-1]["error"] = "database_error"

        self.stdout.write(json.dumps(outcomes, sort_keys=True))
