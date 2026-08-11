"""Weight-only measurement behavior tests."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.measurements.models import Measurement
from config.schema import schema

User = get_user_model()


def _user(email: str):
    """Create a user suitable for measurement tests."""
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


def _context(user):
    """Create an authenticated GraphQL context."""
    return SimpleNamespace(request=SimpleNamespace(user=user))


def test_unsaved_weight_only_measurement_has_no_derived_values():
    """An entry cannot derive body composition before it has a user history."""
    measurement = Measurement(weight=Decimal("75"), body_fat_perc=None)

    assert measurement.calculation_body_fat_perc is None
    assert measurement.bmr == Decimal("0")
    assert measurement.fat_kg == Decimal("0")


@pytest.mark.django_db
def test_create_weight_only_uses_latest_body_fat_for_calculations():
    """A weight-only entry keeps body fat blank but reuses it for BMR."""
    user = _user("weight-only@example.com")
    other_user = _user("other-weight-only@example.com")
    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20"), weight=Decimal("80")
    )
    Measurement.objects.create(
        user=other_user,
        body_fat_perc=Decimal("10"),
        weight=Decimal("90"),
    )

    result = schema.execute_sync(
        """
            mutation WeightOnly($weight: Float!) {
                createMeasurement(weight: $weight) {
                    id
                    bodyFatPerc
                    weight
                    bmr
                    fatKg
                }
            }
        """,
        variable_values={"weight": 75.0},
        context_value=_context(user),
    )

    assert result.errors is None
    assert result.data["createMeasurement"] == {
        "id": result.data["createMeasurement"]["id"],
        "bodyFatPerc": None,
        "weight": 75.0,
        "bmr": 1666.0,
        "fatKg": 15.0,
    }
    persisted = Measurement.objects.get(
        pk=result.data["createMeasurement"]["id"]
    )
    assert persisted.body_fat_perc is None


@pytest.mark.django_db
def test_first_weight_only_measurement_has_no_body_fat_calculations():
    """Calculations remain unavailable until body fat has been recorded."""
    user = _user("first-weight-only@example.com")

    result = schema.execute_sync(
        """
            mutation {
                createMeasurement(weight: 75) {
                    bodyFatPerc
                    bmr
                    fatKg
                }
            }
        """,
        context_value=_context(user),
    )

    assert result.errors is None
    assert result.data["createMeasurement"] == {
        "bodyFatPerc": None,
        "bmr": None,
        "fatKg": None,
    }


@pytest.mark.django_db
def test_update_can_clear_body_fat_and_reuse_previous_value():
    """Clearing body fat keeps the stored value blank and BMR calculable."""
    user = _user("clear-body-fat@example.com")
    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("18"), weight=Decimal("80")
    )
    measurement = Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20"), weight=Decimal("78")
    )

    result = schema.execute_sync(
        """
            mutation ClearBodyFat($id: ID!) {
                updateMeasurement(id: $id, weight: 75) {
                    bodyFatPerc
                    bmr
                    fatKg
                }
            }
        """,
        variable_values={"id": str(measurement.id)},
        context_value=_context(user),
    )

    assert result.errors is None
    assert result.data["updateMeasurement"] == {
        "bodyFatPerc": None,
        "bmr": 1698.4,
        "fatKg": 13.5,
    }
    measurement.refresh_from_db()
    assert measurement.body_fat_perc is None
    assert measurement.weight == Decimal("75.0")
