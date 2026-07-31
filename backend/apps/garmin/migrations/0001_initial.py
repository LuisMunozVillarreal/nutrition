"""Initial migration for Garmin integration models."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
        ("plans", "0032_alter_day_carbs_g_alter_day_carbs_g_goal_and_more"),
        ("exercises", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GarminConnection",
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
                ("provider", models.CharField(default="garmin", max_length=32)),
                (
                    "provider_account_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "provider_scopes",
                    models.JSONField(blank=True, default=list),
                ),
                (
                    "access_token_encrypted",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "refresh_token_encrypted",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "access_token_expires_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "last_synced_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("last_sync_summary", models.JSONField(blank=True, default=dict)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="garmin_connection",
                        to="users.user",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="GarminOAuthState",
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
                (
                    "provider",
                    models.CharField(default="garmin", max_length=32),
                ),
                (
                    "state_hash",
                    models.CharField(max_length=64, unique=True),
                ),
                (
                    "expires_at",
                    models.DateTimeField(),
                ),
                (
                    "consumed_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="garmin_oauth_states",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "provider"], name="garmin_state_user_p"),
                    models.Index(fields=["expires_at"], name="garmin_state_expires"),
                ],
            },
        ),
        migrations.CreateModel(
            name="GarminActivity",
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
                (
                    "provider_activity_id",
                    models.CharField(max_length=255),
                ),
                (
                    "provider_activity_type",
                    models.CharField(max_length=64),
                ),
                (
                    "provider_account_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "started_at",
                    models.DateTimeField(),
                ),
                (
                    "kcals",
                    models.PositiveIntegerField(),
                ),
                (
                    "duration_seconds",
                    models.PositiveIntegerField(),
                ),
                (
                    "distance",
                    models.DecimalField(decimal_places=2, max_digits=10),
                ),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activities",
                        to="garmin.garminconnection",
                    ),
                ),
                (
                    "day",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="garmin_activities",
                        to="plans.day",
                    ),
                ),
                (
                    "exercise",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="garmin_activity",
                        to="exercises.exercise",
                    ),
                ),
            ],
            options={
                "unique_together": {("connection", "provider_activity_id")},
                "indexes": [
                    models.Index(
                        fields=["connection", "provider_activity_id"],
                        name="garmin_activity_conn_act_id",
                    ),
                    models.Index(fields=["day"], name="garmin_activity_day"),
                ],
            },
        ),
    ]
