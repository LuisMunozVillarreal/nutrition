"""Tests for secure E2E lifecycle input."""

import io

import pytest
from django.utils import timezone

from apps.foods.models import CupboardItem, Food, FoodProduct, Recipe
from apps.garmin.models import GarminConnection
from apps.measurements.models import Measurement
from apps.plans.models import WeekPlan
from apps.users.models import User
from scripts.e2e_lifecycle import LifecyclePayload, read_lifecycle_payload
from scripts.manage_e2e_users import cleanup_accounts, seed_accounts


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
