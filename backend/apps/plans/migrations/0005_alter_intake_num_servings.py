# Generated by Django 4.2 on 2023-06-23 23:40

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("plans", "0004_remove_day_calories_remove_intake_calories_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="intake",
            name="num_servings",
            field=models.DecimalField(
                decimal_places=1, default=1, max_digits=10
            ),
        ),
    ]