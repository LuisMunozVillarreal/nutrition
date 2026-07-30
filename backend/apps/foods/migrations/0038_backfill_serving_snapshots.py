"""Restartably backfill recipe and cupboard serving snapshots."""

from decimal import Decimal

from django.db import migrations, models, transaction
from django.db.models import Case, F, Q, Value, When

BATCH_SIZE = 500
CONTEXTUAL_SERVING_UNITS = {"container", "serving"}


def _concrete_serving_size(serving):
    """Reconstruct a serving's concrete amount from historical fields."""
    if serving.serving_unit == "container":
        return serving.food.size
    if serving.serving_unit == "serving":
        if not serving.food.num_servings:
            return Decimal("0")
        return serving.food.size / serving.food.num_servings
    return serving.serving_size


def _ingredient_snapshot(ingredient):
    """Derive a concrete amount and unit from historical persisted fields."""
    serving = ingredient.food
    amount = _concrete_serving_size(serving) * ingredient.num_servings
    unit = serving.serving_unit
    if unit in CONTEXTUAL_SERVING_UNITS:
        unit = serving.food.size_unit
    return amount, unit


def _backfill_ingredient_snapshots(ingredient_model, database):
    """Fill ingredient snapshot pairs in bounded conditional updates."""
    ingredients = ingredient_model.objects.using(database)
    pending = Q(size_snapshot__isnull=True) | Q(
        size_snapshot_unit__isnull=True
    )
    while True:
        with transaction.atomic(using=database):
            batch = list(
                ingredients.select_for_update()
                .filter(pending)
                .select_related("food__food")
                .order_by("pk")[:BATCH_SIZE]
            )
            if not batch:
                break
            snapshots = {
                ingredient.pk: _ingredient_snapshot(ingredient)
                for ingredient in batch
            }
            amount_cases = [
                When(
                    pk=ingredient.pk,
                    size_snapshot__isnull=True,
                    then=Value(snapshots[ingredient.pk][0]),
                )
                for ingredient in batch
            ]
            unit_cases = [
                When(
                    pk=ingredient.pk,
                    size_snapshot_unit__isnull=True,
                    then=Value(snapshots[ingredient.pk][1]),
                )
                for ingredient in batch
            ]
            batch_pks = [ingredient.pk for ingredient in batch]
            updated = ingredients.filter(
                pending,
                pk__in=batch_pks,
            ).update(
                size_snapshot=Case(
                    *amount_cases,
                    default=F("size_snapshot"),
                    output_field=models.DecimalField(
                        max_digits=20, decimal_places=10
                    ),
                ),
                size_snapshot_unit=Case(
                    *unit_cases,
                    default=F("size_snapshot_unit"),
                    output_field=models.CharField(max_length=20),
                ),
            )
            if (
                not updated
                and ingredients.filter(
                    pending,
                    pk__in=batch_pks,
                ).exists()
            ):
                raise RuntimeError(
                    "ingredient snapshot backfill made no progress"
                )


def _consumption_snapshot(consumption):
    """Derive a concrete amount and unit from historical persisted fields."""
    serving = consumption.serving
    num_servings = consumption.num_servings
    if num_servings is None:
        num_servings = (
            consumption.intake.num_servings
            if consumption.intake_id is not None
            else Decimal("1")
        )
    amount = _concrete_serving_size(serving) * num_servings
    unit = serving.serving_unit
    if unit in CONTEXTUAL_SERVING_UNITS:
        unit = serving.food.size_unit
    return amount, unit


def _backfill_consumption_snapshots(consumption_model, database):
    """Fill consumption snapshots in bounded conditional updates."""
    consumptions = consumption_model.objects.using(database)
    pending = Q(consumed_amount__isnull=True) | Q(consumed_unit__isnull=True)
    while True:
        with transaction.atomic(using=database):
            batch = list(
                consumptions.select_for_update()
                .filter(pending)
                .select_related("serving__food", "intake")
                .order_by("pk")[:BATCH_SIZE]
            )
            if not batch:
                break
            snapshots = {
                consumption.pk: _consumption_snapshot(consumption)
                for consumption in batch
            }
            amount_cases = [
                When(
                    pk=consumption.pk,
                    consumed_amount__isnull=True,
                    then=Value(snapshots[consumption.pk][0]),
                )
                for consumption in batch
            ]
            unit_cases = [
                When(
                    pk=consumption.pk,
                    consumed_unit__isnull=True,
                    then=Value(snapshots[consumption.pk][1]),
                )
                for consumption in batch
            ]
            batch_pks = [consumption.pk for consumption in batch]
            updated = consumptions.filter(
                pending,
                pk__in=batch_pks,
            ).update(
                consumed_amount=Case(
                    *amount_cases,
                    default=F("consumed_amount"),
                    output_field=models.DecimalField(
                        max_digits=20, decimal_places=10
                    ),
                ),
                consumed_unit=Case(
                    *unit_cases,
                    default=F("consumed_unit"),
                    output_field=models.CharField(max_length=20),
                ),
            )
            if (
                not updated
                and consumptions.filter(
                    pending,
                    pk__in=batch_pks,
                ).exists()
            ):
                raise RuntimeError(
                    "consumption snapshot backfill made no progress"
                )


def backfill_serving_snapshots(apps, schema_editor):
    """Fill null snapshots using bounded, independently committed batches."""
    database = schema_editor.connection.alias
    _backfill_ingredient_snapshots(
        apps.get_model("foods", "RecipeIngredient"), database
    )
    _backfill_consumption_snapshots(
        apps.get_model("foods", "CupboardItemConsumption"), database
    )


class Migration(migrations.Migration):
    """Run snapshot data work independently of schema DDL."""

    atomic = False

    dependencies = [("foods", "0037_backfill_consumption_num_servings")]

    operations = [
        migrations.RunPython(
            backfill_serving_snapshots,
            reverse_code=migrations.RunPython.noop,
            atomic=False,
        ),
    ]
