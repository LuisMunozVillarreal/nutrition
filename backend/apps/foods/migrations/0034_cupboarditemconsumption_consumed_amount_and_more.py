"""Expand recipe and cupboard links with nullable serving snapshots."""

from django.db import migrations, models

UNIT_CHOICES = [
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
]


class Migration(migrations.Migration):
    """Record short schema expansion before restartable data work."""

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
                choices=UNIT_CHOICES,
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
        migrations.AddField(
            model_name="recipeingredient",
            name="size_snapshot_unit",
            field=models.CharField(
                choices=UNIT_CHOICES,
                editable=False,
                max_length=20,
                null=True,
            ),
        ),
    ]
