# Generated by Django 5.1.3 on 2024-12-20 20:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0023_day_completed"),
    ]

    operations = [
        migrations.AddField(
            model_name="weekplan",
            name="completed",
            field=models.BooleanField(
                default=False,
                editable=False,
                help_text="Indicates whether the week has been completed and has all the required information inputted.",
            ),
        ),
    ]