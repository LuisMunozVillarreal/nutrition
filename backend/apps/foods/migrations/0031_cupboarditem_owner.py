"""Add cupboard ownership and quarantine unattributable legacy inventory."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assign_legacy_cupboard_owner(apps, schema_editor):
    """Leave legacy rows unowned because historical attribution is unknowable.

    Application queries require an exact owner match, so nullable legacy rows
    form an explicit quarantine until a separate, evidence-based reconciliation
    process assigns them.
    """
    del apps, schema_editor


class Migration(migrations.Migration):
    """Add the cupboard item owner relationship."""

    dependencies = [
        ("foods", "0030_alter_food_carbs_g_alter_food_fat_g_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cupboarditem",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cupboard_items",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            assign_legacy_cupboard_owner,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
