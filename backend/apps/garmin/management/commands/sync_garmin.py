"""Sync Garmin command."""

from django.core.management.base import BaseCommand

from apps.garmin.sync import sync_activities
from apps.users.models import User


class Command(BaseCommand):
    """Sync Garmin activities command."""

    help = "Syncs Garmin activities for all connected users."

    def handle(self, *args, **options) -> None:
        """Handle command execution."""
        users = User.objects.filter(garmin_credential__isnull=False)
        self.stdout.write(f"Syncing Garmin for {users.count()} users...")

        for user in users:
            self.stdout.write(f"Syncing user {user.email}...")
            sync_activities(user)

        self.stdout.write(self.style.SUCCESS("Successfully synced Garmin activities."))
