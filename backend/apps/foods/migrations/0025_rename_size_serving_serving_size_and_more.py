# Generated by Django 5.1.6 on 2025-02-08 20:23

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("foods", "0024_rename_weight_food_size_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="serving",
            old_name="size",
            new_name="serving_size",
        ),
        migrations.RenameField(
            model_name="serving",
            old_name="unit",
            new_name="serving_unit",
        ),
    ]
