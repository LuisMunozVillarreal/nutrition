# Generated by Django 5.1.3 on 2024-11-17 16:32

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("foods", "0012_alter_serving_size"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serving",
            name="size",
            field=models.PositiveIntegerField(
                default=100,
                help_text="Size is the amount of units in the serving. For example, if the unit is grams and the size is 100, it means 100g. When the serving unit and the food weight unit is the same, then the weight of the serving is the same as the weight of the food. However, when the unit of the serving is 'container' or 'serving', then the weight will most certainly differ from the size, e.g.: size 1 unit container weights 320g.",
            ),
        ),
        migrations.CreateModel(
            name="CupboardItemConsumption",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "num_servings",
                    models.DecimalField(
                        decimal_places=1, default=1, max_digits=10
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="servings",
                        to="foods.cupboarditem",
                    ),
                ),
                (
                    "serving",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cupboard_items",
                        to="foods.serving",
                    ),
                ),
            ],
        ),
        migrations.DeleteModel(
            name="CupboardItemServing",
        ),
    ]