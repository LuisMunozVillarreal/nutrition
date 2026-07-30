"""Expand cupboard items with a nullable manual-consumption baseline."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Record short schema expansion before restartable data work."""

    dependencies = [("foods", "0031_cupboarditem_owner")]

    operations = [
        migrations.AddField(
            model_name="cupboarditem",
            name="manual_consumed_perc",
            field=models.DecimalField(
                decimal_places=2,
                help_text=(
                    "Consumption entered manually, before linked recipe and "
                    "intake consumptions are added."
                ),
                max_digits=10,
                null=True,
            ),
        ),
    ]
