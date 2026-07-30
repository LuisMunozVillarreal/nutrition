"""Preserve manual cupboard consumption separately from linked usage."""

from django.db import migrations, models
from django.db.models import F


def initialize_manual_consumed_perc(apps, schema_editor):
    """Keep unlinked totals as baselines without double-counting linked rows."""
    del schema_editor
    cupboard_item = apps.get_model("foods", "CupboardItem")
    cupboard_item.objects.filter(consumptions__isnull=True).update(
        manual_consumed_perc=F("consumed_perc")
    )


class Migration(migrations.Migration):
    """Add the durable manual cupboard consumption baseline."""

    dependencies = [("foods", "0031_cupboarditem_owner")]

    operations = [
        migrations.AddField(
            model_name="cupboarditem",
            name="manual_consumed_perc",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text=(
                    "Consumption entered manually, before linked recipe and "
                    "intake consumptions are added."
                ),
                max_digits=10,
            ),
        ),
        migrations.RunPython(
            initialize_manual_consumed_perc,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
