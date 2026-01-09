"""Sync Garmin command."""

from typing import Any

from django.core.management.base import BaseCommand

from apps.garmin.sync import sync_activities
from apps.users.models import User


class Command(BaseCommand):
    """Sync Garmin activities command."""

    help = "Syncs Garmin activities for all connected users."

    def handle(self, *args: Any, **options: Any) -> None:
        """Handle command execution.

        Args:
            *args (Any): positional arguments.
            **options (Any): keyword arguments.
        """
        users = User.objects.filter(
            garmin_credential__isnull=False
        )  # type: ignore[misc]
        self.stdout.write(f"Syncing Garmin for {users.count()} users...")

        for user in users:
            self.stdout.write(f"Syncing user {user.email}...")
            # mypy doesn't resolve reverse OneToOne well, so we ignore
            sync_activities(user)  # type: ignore[arg-type]

        self.stdout.write(
            self.style.SUCCESS("Successfully synced Garmin activities.")
        )
