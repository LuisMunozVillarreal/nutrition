"""Join Garmin activity provenance and browser-auth migration histories."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("health_sync", "0005_activityimport"),
        ("health_sync", "0007_healthsyncrefreshclaim"),
    ]

    operations = []
