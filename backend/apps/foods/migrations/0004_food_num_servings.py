# Generated by Django 4.2 on 2023-06-23 23:14

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("foods", "0003_remove_food_calories_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="food",
            name="num_servings",
            field=models.PositiveIntegerField(default=1),
        ),
    ]