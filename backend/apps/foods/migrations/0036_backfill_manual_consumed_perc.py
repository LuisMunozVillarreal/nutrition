"""Restartably backfill manual cupboard-consumption baselines."""

from decimal import Decimal

from django.db import migrations, models, transaction
from django.db.models import Case, F, Value, When
from pint import UnitRegistry
from pint.errors import DimensionalityError

CONTEXTUAL_UNITS = frozenset({"container", "serving", "unit"})
BATCH_SIZE = 500

# Freeze the concrete values persisted by the historical model into this data
# migration. An empty registry avoids Pint's built-in aliases (notably ``c``
# for the speed of light) and keeps these conversion factors independent of
# later runtime-unit changes.
UNIT_DEFINITIONS = (
    "g = [mass]",
    "mg = 0.001 g",
    "kg = 1000 g",
    "oz = 28.349523125 g",
    "lb = 16 oz",
    "l = [volume]",
    "ml = 0.001 l",
    "cl = 0.01 l",
    "floz = 29.573529562499985 ml",
    "c = 8 floz",
    "tsp = 4.92892159375 ml",
    "tbsp = 3 tsp",
    "pt = 16 floz",
)
UREG = UnitRegistry(None)
for unit_definition in UNIT_DEFINITIONS:
    UREG.define(unit_definition)


def _serving_amount(consumption):
    """Return a historical link's amount and concrete unit."""
    serving = consumption.serving
    quantity = (
        consumption.intake.num_servings
        if consumption.intake_id is not None
        else Decimal("1")
    )
    if serving.serving_unit == "container":
        return serving.food.size * quantity, serving.food.size_unit
    if serving.serving_unit == "serving":
        if not serving.food.num_servings:
            return Decimal("0"), serving.food.size_unit
        return (
            serving.food.size * quantity / serving.food.num_servings,
            serving.food.size_unit,
        )
    return serving.serving_size * quantity, serving.serving_unit


def _add_linked_consumption(
    linked_totals, ambiguous_items, consumption, items
):
    """Accumulate one historical link without retaining unbounded fan-out."""
    item = items[consumption.item_id]
    if item.food.size is None or item.food.size <= 0:
        ambiguous_items.add(item.pk)
        return
    amount, unit = _serving_amount(consumption)
    stock_unit = item.food.size_unit
    if unit in CONTEXTUAL_UNITS or stock_unit in CONTEXTUAL_UNITS:
        if unit != stock_unit:
            ambiguous_items.add(item.pk)
            return
        converted_amount = amount
    else:
        try:
            converted_amount = (
                UREG.Quantity(amount * UREG(unit)).to(stock_unit).m
            )
        except DimensionalityError:
            ambiguous_items.add(item.pk)
            return
    linked_totals[item.pk] += converted_amount * 100 / item.food.size


def _linked_totals_for_batch(consumption_model, database, batch):
    """Read related links in independently bounded keyset pages."""
    items = {item.pk: item for item in batch}
    linked_totals = {item.pk: Decimal("0") for item in batch}
    ambiguous_items = set()
    last_pk = None

    while True:
        filters = {"item_id__in": items}
        if last_pk is not None:
            filters["pk__gt"] = last_pk
        links = list(
            consumption_model.objects.using(database)
            .filter(**filters)
            .select_related("serving__food", "intake")
            .order_by("pk")[:BATCH_SIZE]
        )
        if not links:
            break
        for consumption in links:
            _add_linked_consumption(
                linked_totals, ambiguous_items, consumption, items
            )
        last_pk = links[-1].pk

    for item_id in ambiguous_items:
        linked_totals[item_id] = items[item_id].consumed_perc
    return linked_totals


def backfill_manual_consumed_perc(apps, schema_editor):
    """Fill only null baselines in bounded, independently committed batches."""
    cupboard_item = apps.get_model("foods", "CupboardItem")
    consumption_model = apps.get_model("foods", "CupboardItemConsumption")
    database = schema_editor.connection.alias
    items = cupboard_item.objects.using(database)

    while True:
        with transaction.atomic(using=database):
            batch = list(
                items.select_for_update(of=("self",))
                .filter(manual_consumed_perc__isnull=True)
                .select_related("food")
                .order_by("pk")[:BATCH_SIZE]
            )
            if not batch:
                break

            linked_totals = _linked_totals_for_batch(
                consumption_model, database, batch
            )
            cases = [
                When(
                    pk=item.pk,
                    then=Value(
                        max(
                            item.consumed_perc - linked_totals[item.pk],
                            Decimal("0"),
                        )
                    ),
                )
                for item in batch
            ]
            batch_pks = [item.pk for item in batch]
            updated = items.filter(
                pk__in=batch_pks,
                manual_consumed_perc__isnull=True,
            ).update(
                manual_consumed_perc=Case(
                    *cases,
                    default=F("manual_consumed_perc"),
                    output_field=models.DecimalField(
                        max_digits=10, decimal_places=2
                    ),
                )
            )
            if (
                not updated
                and items.filter(
                    pk__in=batch_pks,
                    manual_consumed_perc__isnull=True,
                ).exists()
            ):
                raise RuntimeError("manual baseline backfill made no progress")


class Migration(migrations.Migration):
    """Run manual baseline data work independently of schema DDL."""

    atomic = False

    dependencies = [
        ("foods", "0035_relax_preview_snapshot_constraints"),
    ]

    operations = [
        migrations.RunPython(
            backfill_manual_consumed_perc,
            reverse_code=migrations.RunPython.noop,
            atomic=False,
        ),
    ]
