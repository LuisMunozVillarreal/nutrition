"""Add and backfill stable recipe and cupboard serving snapshots."""

from decimal import Decimal

from django.db import migrations, models

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


def backfill_serving_snapshots(apps, schema_editor):
    """Populate deterministic snapshots before the new fields become non-null."""
    consumption_model = apps.get_model("foods", "CupboardItemConsumption")
    ingredient_model = apps.get_model("foods", "RecipeIngredient")
    database = schema_editor.connection.alias

    ingredients = (
        ingredient_model.objects.using(database)
        .select_related("food__food")
        .all()
    )
    for ingredient in ingredients.iterator():
        size_snapshot = (
            _concrete_serving_size(ingredient.food) * ingredient.num_servings
        )
        ingredient_model.objects.using(database).filter(
            pk=ingredient.pk
        ).update(size_snapshot=size_snapshot)

    consumptions = (
        consumption_model.objects.using(database)
        .select_related("serving__food")
        .all()
    )
    for consumption in consumptions.iterator():
        serving = consumption.serving
        consumed_amount = (
            _concrete_serving_size(serving) * consumption.num_servings
        )
        consumed_unit = serving.serving_unit
        if consumed_unit in CONTEXTUAL_SERVING_UNITS:
            consumed_unit = serving.food.size_unit
        consumption_model.objects.using(database).filter(
            pk=consumption.pk
        ).update(
            consumed_amount=consumed_amount,
            consumed_unit=consumed_unit,
        )


class Migration(migrations.Migration):
    """Add and populate immutable serving amount snapshots."""

    dependencies = [
        ("foods", "0033_cupboarditemconsumption_num_servings"),
    ]

    operations = [
        migrations.AddField(
            model_name="cupboarditemconsumption",
            name="consumed_amount",
            field=models.DecimalField(
                decimal_places=10,
                editable=False,
                max_digits=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="cupboarditemconsumption",
            name="consumed_unit",
            field=models.CharField(
                choices=[
                    ("mg", "milligram(s)"),
                    ("g", "gram(s)"),
                    ("kg", "kilogram(s)"),
                    ("oz", "ounce(s)"),
                    ("lb", "pound(s)"),
                    ("ml", "millilitre(s)"),
                    ("cl", "centilitre(s)"),
                    ("l", "litre(s)"),
                    ("c", "cup(s)"),
                    ("floz", "fluid ounce(s)"),
                    ("tbsp", "tablespoon(s)"),
                    ("tsp", "teaspoon(s)"),
                    ("pt", "pint(s)"),
                    ("unit", "unit(s)"),
                    ("serving", "serving(s)"),
                    ("container", "container(s)"),
                ],
                editable=False,
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="recipeingredient",
            name="size_snapshot",
            field=models.DecimalField(
                decimal_places=10,
                editable=False,
                help_text="Total ingredient size captured from its serving when saved.",
                max_digits=20,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_serving_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="cupboarditemconsumption",
            name="consumed_amount",
            field=models.DecimalField(
                decimal_places=10,
                default=0,
                editable=False,
                max_digits=20,
            ),
        ),
        migrations.AlterField(
            model_name="cupboarditemconsumption",
            name="consumed_unit",
            field=models.CharField(
                choices=[
                    ("mg", "milligram(s)"),
                    ("g", "gram(s)"),
                    ("kg", "kilogram(s)"),
                    ("oz", "ounce(s)"),
                    ("lb", "pound(s)"),
                    ("ml", "millilitre(s)"),
                    ("cl", "centilitre(s)"),
                    ("l", "litre(s)"),
                    ("c", "cup(s)"),
                    ("floz", "fluid ounce(s)"),
                    ("tbsp", "tablespoon(s)"),
                    ("tsp", "teaspoon(s)"),
                    ("pt", "pint(s)"),
                    ("unit", "unit(s)"),
                    ("serving", "serving(s)"),
                    ("container", "container(s)"),
                ],
                default="",
                editable=False,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="recipeingredient",
            name="size_snapshot",
            field=models.DecimalField(
                decimal_places=10,
                default=0,
                editable=False,
                help_text="Total ingredient size captured from its serving when saved.",
                max_digits=20,
            ),
        ),
    ]
