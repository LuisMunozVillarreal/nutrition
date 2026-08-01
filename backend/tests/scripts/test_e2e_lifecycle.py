"""Tests for secure E2E lifecycle input."""

import io
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.foods.models import CupboardItem, Food, FoodProduct, Recipe
from apps.garmin.models import GarminActivity, GarminConnection
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from apps.users.models import User
from scripts.e2e_lifecycle import LifecyclePayload, read_lifecycle_payload
from scripts.manage_e2e_users import (
    cleanup_accounts,
    cleanup_garmin_connection,
    reset_garmin_connection,
    seed_accounts,
)


def test_read_lifecycle_payload_reads_structured_stdin():
    """Lifecycle data is decoded from stdin without environment variables."""
    stream = io.StringIO(
        '{"regular_email":"regular@example.com",'
        '"regular_password":"regular-sentinel",'
        '"staff_email":"staff@example.com",'
        '"staff_password":"staff-sentinel",'
        '"run_marker":"__e2e_run_0123456789abcdef0123456789abcdef__"}'
    )

    payload = read_lifecycle_payload(stream)

    assert payload.regular_email == "regular@example.com"
    assert payload.regular_password == "regular-sentinel"
    assert payload.staff_email == "staff@example.com"
    assert payload.staff_password == "staff-sentinel"
    assert payload.run_marker == "__e2e_run_0123456789abcdef0123456789abcdef__"


def test_lifecycle_payload_repr_redacts_passwords():
    """Diagnostic representations do not expose either generated password."""
    payload = LifecyclePayload(
        regular_email="regular@example.com",
        regular_password="regular-sentinel",
        staff_email="staff@example.com",
        staff_password="staff-sentinel",
        run_marker="__e2e_run_0123456789abcdef0123456789abcdef__",
    )

    representation = repr(payload)

    assert "regular-sentinel" not in representation
    assert "staff-sentinel" not in representation


@pytest.mark.django_db
def test_garmin_scenario_reruns_reset_and_clean_placeholder_connection():
    """Each destructive scenario starts cleanly connected and leaves no fixture."""
    payload = LifecyclePayload(
        regular_email="regular-rerun@example.com",
        regular_password="regular-sentinel",
        staff_email="staff-rerun@example.com",
        staff_password="staff-sentinel",
        run_marker="__e2e_run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa__",
    )
    seed_accounts(payload)
    regular = User.objects.get(email=payload.regular_email)
    connection = GarminConnection.objects.get(user=regular)
    measurement = Measurement.objects.create(
        user=regular,
        weight=80,
        body_fat_perc=20,
    )
    plan = WeekPlan.objects.create(
        user=regular,
        measurement=measurement,
        start_date=timezone.localdate(),
        protein_g_kg=2,
        fat_perc=25,
    )
    day = Day.objects.filter(plan=plan).first()
    assert day is not None
    manual_exercise = Exercise.objects.create(
        day=day,
        time=time(8),
        type=Exercise.EXERCISE_WALK,
        kcals=50,
    )
    derived_exercise = Exercise.objects.create(
        day=day,
        time=time(9),
        type=Exercise.EXERCISE_CYCLE,
        kcals=100,
        duration=timedelta(minutes=20),
        distance=Decimal("5.00"),
    )
    GarminActivity.objects.create(
        connection=connection,
        provider_activity_id="stale-e2e-activity",
        provider_activity_type="cycle",
        day=day,
        exercise=derived_exercise,
        started_at=timezone.now(),
        kcals=100,
        duration_seconds=1200,
        distance=Decimal("5.00"),
    )
    connection.clear_tokens()
    connection.save()

    reset_garmin_connection(payload)
    reset_garmin_connection(payload)

    connection = GarminConnection.objects.get(user=regular)
    assert connection.is_connected
    assert connection.has_refresh_token
    assert connection.status == GarminConnection.Status.ACTIVE
    assert connection.access_token_encrypted == ""
    assert connection.provider_account_id == ""
    assert connection.provider_scopes == []
    assert GarminConnection.objects.filter(user=regular).count() == 1
    assert not GarminActivity.objects.filter(connection=connection).exists()
    assert not Exercise.objects.filter(pk=derived_exercise.pk).exists()
    assert Exercise.objects.filter(pk=manual_exercise.pk).exists()

    cleanup_exercise = Exercise.objects.create(
        day=day,
        time=time(10),
        type=Exercise.EXERCISE_RUN,
        kcals=75,
    )
    GarminActivity.objects.create(
        connection=connection,
        provider_activity_id="cleanup-e2e-activity",
        provider_activity_type="run",
        day=day,
        exercise=cleanup_exercise,
        started_at=timezone.now(),
        kcals=75,
        duration_seconds=600,
        distance=Decimal("2.00"),
    )

    cleanup_garmin_connection(payload)
    cleanup_garmin_connection(payload)
    assert not GarminConnection.objects.filter(user=regular).exists()
    assert not Exercise.objects.filter(pk=derived_exercise.pk).exists()
    assert not Exercise.objects.filter(pk=cleanup_exercise.pk).exists()
    assert Exercise.objects.filter(pk=manual_exercise.pk).exists()


@pytest.mark.django_db
def test_cleanup_removes_only_each_runs_shared_and_owned_fixtures():
    """Two lifecycles leave no run rows and preserve similar catalog names."""
    retained = FoodProduct.objects.create(name="Cypress Milk")

    for index, token in enumerate(("1" * 32, "2" * 32), start=1):
        marker = f"__e2e_run_{token}__"
        payload = LifecyclePayload(
            regular_email=f"regular-{index}@example.com",
            regular_password="regular-sentinel",
            staff_email=f"staff-{index}@example.com",
            staff_password="staff-sentinel",
            run_marker=marker,
        )
        seed_accounts(payload)
        regular = User.objects.get(email=payload.regular_email)
        garmin_connection = GarminConnection.objects.get(user=regular)
        assert garmin_connection.is_connected
        assert garmin_connection.has_refresh_token
        product = FoodProduct.objects.create(name=f"Cypress Milk {marker}")
        Recipe.objects.create(name=f"Cypress Recipe {marker}")
        CupboardItem.objects.create(
            owner=regular,
            food=product,
            purchased_at=timezone.now(),
        )
        measurement = Measurement.objects.create(
            user=regular,
            weight=80,
            body_fat_perc=20,
        )
        WeekPlan.objects.create(
            user=regular,
            measurement=measurement,
            start_date=timezone.localdate(),
            protein_g_kg=2,
            fat_perc=25,
        )

        cleanup_accounts(payload)
        cleanup_accounts(payload)

        assert not Food.objects.filter(name__endswith=marker).exists()
        assert not User.objects.filter(
            email__in=[payload.regular_email, payload.staff_email]
        ).exists()
        assert not CupboardItem.objects.filter(owner=regular).exists()
        assert not WeekPlan.objects.filter(user=regular).exists()
        assert not GarminConnection.objects.filter(user=regular).exists()

    assert FoodProduct.objects.filter(pk=retained.pk).exists()
