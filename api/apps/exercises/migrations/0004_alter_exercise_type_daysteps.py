# Generated by Django 4.2 on 2023-05-06 00:02

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("exercises", "0003_exercise_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exercise",
            name="type",
            field=models.CharField(
                choices=[
                    ("walk", "Walk"),
                    ("run", "Run"),
                    ("cycle", "Cycle"),
                    ("gym", "Gym"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DaySteps",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("day", models.DateField()),
                ("steps", models.PositiveIntegerField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="steps",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]