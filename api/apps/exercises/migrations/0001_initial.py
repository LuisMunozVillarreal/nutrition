# Generated by Django 4.2 on 2023-05-05 22:17

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Exercise",
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
                ("datetime", models.DateTimeField()),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("walk", "Walk"),
                            ("run", "Run"),
                            ("cycle", "Cycle"),
                        ],
                        max_length=20,
                    ),
                ),
                ("kcals", models.PositiveIntegerField()),
                ("duration", models.DurationField(blank=True, null=True)),
                (
                    "distance",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        verbose_name="Distance (km)",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]