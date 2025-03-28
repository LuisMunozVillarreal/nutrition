# Generated by Django 5.1.6 on 2025-02-09 10:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("foods", "0028_food_abv_perc_recipeingredient_abv_perc_and_more"),
        ("plans", "0030_day_abv_perc_intake_abv_perc"),
    ]

    operations = [
        migrations.AlterField(
            model_name="intake",
            name="food",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="intakes",
                to="foods.serving",
            ),
        ),
    ]
