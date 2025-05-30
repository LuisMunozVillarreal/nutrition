# Generated by Django 5.1.3 on 2024-12-20 20:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0022_rename_excercises_exc_day_exercises_exc_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="day",
            name="completed",
            field=models.BooleanField(
                default=False,
                editable=False,
                help_text="Indicates whether the day has been completed and has all the required information inputted.",
            ),
        ),
    ]
