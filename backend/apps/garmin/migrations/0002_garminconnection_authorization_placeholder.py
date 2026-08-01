"""Track callback-created Garmin connection placeholders."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add explicit placeholder provenance for safe callback cleanup."""

    dependencies = [
        ("garmin", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="garminconnection",
            name="authorization_placeholder",
            field=models.BooleanField(default=False),
        ),
    ]
