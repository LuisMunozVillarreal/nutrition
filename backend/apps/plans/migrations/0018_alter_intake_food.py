# Generated by Django 5.1.3 on 2024-12-01 22:01

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("foods", "0020_alter_food_calcium_perc_alter_food_carbs_g_and_more"),
        ("plans", "0017_alter_intake_food"),
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
                to="foods.serving",
            ),
        ),
    ]