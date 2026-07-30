"""Restartably backfill cupboard-consumption serving quantities."""

from decimal import Decimal

from django.db import migrations, models, transaction
from django.db.models import Case, F, Value, When

BATCH_SIZE = 500


def backfill_consumption_num_servings(apps, schema_editor):
    """Fill only null quantities in bounded, independently committed batches."""
    consumption_model = apps.get_model("foods", "CupboardItemConsumption")
    database = schema_editor.connection.alias
    consumptions = consumption_model.objects.using(database)

    while True:
        with transaction.atomic(using=database):
            batch = list(
                consumptions.select_for_update()
                .filter(num_servings__isnull=True)
                .select_related("intake")
                .order_by("pk")[:BATCH_SIZE]
            )
            if not batch:
                break

            cases = [
                When(
                    pk=consumption.pk,
                    then=Value(
                        consumption.intake.num_servings
                        if consumption.intake_id is not None
                        else Decimal("1")
                    ),
                )
                for consumption in batch
            ]
            batch_pks = [consumption.pk for consumption in batch]
            updated = consumptions.filter(
                pk__in=batch_pks,
                num_servings__isnull=True,
            ).update(
                num_servings=Case(
                    *cases,
                    default=F("num_servings"),
                    output_field=models.DecimalField(
                        max_digits=10, decimal_places=1
                    ),
                )
            )
            if (
                not updated
                and consumptions.filter(
                    pk__in=batch_pks,
                    num_servings__isnull=True,
                ).exists()
            ):
                raise RuntimeError("quantity backfill made no progress")


class Migration(migrations.Migration):
    """Run quantity data work independently of schema DDL."""

    atomic = False

    dependencies = [("foods", "0036_backfill_manual_consumed_perc")]

    operations = [
        migrations.RunPython(
            backfill_consumption_num_servings,
            reverse_code=migrations.RunPython.noop,
            atomic=False,
        ),
    ]
