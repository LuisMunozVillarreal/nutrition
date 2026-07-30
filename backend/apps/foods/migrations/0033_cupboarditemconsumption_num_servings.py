"""Capture historical serving quantities for cupboard consumption links."""

from decimal import Decimal

from django.db import migrations, models


def backfill_consumption_num_servings(apps, schema_editor):
    """Snapshot intake quantities and conservatively default untraceable links."""
    consumption_model = apps.get_model("foods", "CupboardItemConsumption")
    database = schema_editor.connection.alias
    consumptions = (
        consumption_model.objects.using(database)
        .select_related("intake")
        .all()
    )
    for consumption in consumptions.iterator():
        num_servings = Decimal("1")
        if consumption.intake_id is not None:
            num_servings = consumption.intake.num_servings
        consumption_model.objects.using(database).filter(
            pk=consumption.pk
        ).update(num_servings=num_servings)


class Migration(migrations.Migration):
    """Add and populate the cupboard consumption serving quantity snapshot."""

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
        migrations.RunPython(
            backfill_consumption_num_servings,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="cupboarditemconsumption",
            name="num_servings",
            field=models.DecimalField(
                decimal_places=1,
                default=1,
                help_text="Serving quantity captured when this consumption was linked.",
                max_digits=10,
            ),
        ),
    ]
