"""Preserve manual cupboard consumption separately from linked usage."""

from decimal import Decimal

from django.db import migrations, models
from pint import UnitRegistry
from pint.errors import DimensionalityError

CONTEXTUAL_UNITS = {"container", "serving", "unit"}
UREG = UnitRegistry()


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
        return (
            serving.food.size * quantity / serving.food.num_servings,
            serving.food.size_unit,
        )
    return serving.serving_size * quantity, serving.serving_unit


def _linked_consumed_perc(item):
    """Reconstruct a historical item's linked percentage without model methods."""
    linked_perc = Decimal("0")
    for consumption in item.consumptions.all():
        amount, unit = _serving_amount(consumption)
        stock_unit = item.food.size_unit
        if unit in CONTEXTUAL_UNITS or stock_unit in CONTEXTUAL_UNITS:
            if unit != stock_unit:
                # The legacy relationship is dimensionally ambiguous. A zero
                # manual baseline is conservative and cannot double-count it.
                return item.consumed_perc
            converted_amount = amount
        else:
            try:
                converted_amount = (
                    UREG.Quantity(amount * UREG(unit)).to(stock_unit).m
                )
            except DimensionalityError:
                return item.consumed_perc
        linked_perc += converted_amount * 100 / item.food.size
    return linked_perc


def initialize_manual_consumed_perc(apps, schema_editor):
    """Set manual baseline to max(stored total minus linked total, zero)."""
    del schema_editor
    cupboard_item = apps.get_model("foods", "CupboardItem")
    items = cupboard_item.objects.select_related("food").prefetch_related(
        "consumptions__serving__food", "consumptions__intake"
    )
    for item in items:
        linked_perc = _linked_consumed_perc(item)
        item.manual_consumed_perc = max(
            item.consumed_perc - linked_perc, Decimal("0")
        )
        item.save(update_fields=["manual_consumed_perc"])


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
