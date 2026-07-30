"""Expand cupboard consumption links with nullable serving quantities."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Record short schema expansion before restartable data work."""

    dependencies = [
        ("foods", "0032_cupboarditem_manual_consumed_perc"),
    ]

    operations = [
        migrations.AddField(
            model_name="cupboarditemconsumption",
            name="num_servings",
            field=models.DecimalField(
                decimal_places=1,
                help_text="Serving quantity captured when this consumption was linked.",
                max_digits=10,
                null=True,
            ),
        ),
    ]
