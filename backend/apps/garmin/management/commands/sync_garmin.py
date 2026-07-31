"""Management command for Garmin activity synchronization."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db import OperationalError, router, transaction

from apps.garmin.services import sync_connection
from apps.garmin.models import GarminConnection


class Command(BaseCommand):
    """Run Garmin sync for one or all active connections."""

    help = "Synchronize Garmin activities for one or all connected users."

    def add_arguments(self, parser):  # type: ignore[override]
        parser.add_argument(
            "--user-id",
            type=int,
            dest="user_id",
            required=False,
            help="Optional user id to sync only one Garmin connection.",
        )

    def handle(self, *args, **options):  # type: ignore[override]
        user_id = options.get("user_id")
        using = router.db_for_write(GarminConnection)
        queryset = GarminConnection.objects.using(using).all()
        if user_id is not None:
            queryset = queryset.filter(user_id=user_id)

        outcomes = []
        for connection in queryset.order_by("pk"):
            try:
                with transaction.atomic(using=using):
                    locked = GarminConnection.objects.select_for_update().using(
                        using
                    ).get(pk=connection.pk)
                    summary = sync_connection(locked)
                    outcomes.append(
                        {
                            "connection_id": locked.pk,
                            "user_id": locked.user_id,
                            "imported": summary.imported,
                            "duplicates": summary.duplicates,
                            "unsupported": summary.unsupported,
                            "invalid": summary.invalid,
                        }
                    )
            except ValueError as exc:
                outcomes.append(
                    {
                        "connection_id": connection.pk,
                        "user_id": connection.user_id,
                        "error": str(exc),
                    }
                )
            except OperationalError as exc:
                outcomes.append(
                    {
                        "connection_id": connection.pk,
                        "user_id": connection.user_id,
                        "error": str(exc),
                    }
                )

        self.stdout.write(json.dumps(outcomes, sort_keys=True))
