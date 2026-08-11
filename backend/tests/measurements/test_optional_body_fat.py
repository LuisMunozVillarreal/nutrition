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
    assert persisted.body_fat_calculation_perc == Decimal("20")


@pytest.mark.django_db
def test_weight_only_calculation_is_stable_when_body_fat_history_changes():
    """A recorded weight keeps the body-fat snapshot selected at entry time."""
    user = _user("stable-weight-only@example.com")
    source = Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20"), weight=Decimal("80")
    )
    result = schema.execute_sync(
        """
            mutation {
                createMeasurement(weight: 75) { id bmr fatKg }
            }
        """,
        context_value=_context(user),
    )
    weight_only = Measurement.objects.get(
        pk=result.data["createMeasurement"]["id"]
    )

    later = Measurement.objects.create(
        user=user, body_fat_perc=Decimal("30"), weight=Decimal("76")
    )
    source.body_fat_perc = Decimal("25")
    source.save(update_fields=["body_fat_perc"])
    later.delete()
    source.delete()
    weight_only.refresh_from_db()

    assert weight_only.body_fat_calculation_perc == Decimal("20")
    assert weight_only.bmr == Decimal("1666.000")
    assert weight_only.fat_kg == Decimal("15.00")


@pytest.mark.django_db
def test_weight_only_measurements_do_not_add_fallback_queries(
    django_assert_num_queries,
):
    """Resolving multiple weight-only rows does not query once per row."""
    user = _user("query-budget-weight-only@example.com")
    for weight in (Decimal("75"), Decimal("76"), Decimal("77")):
        Measurement.objects.create(
            user=user,
            body_fat_perc=None,
            body_fat_calculation_perc=Decimal("20"),
            weight=weight,
        )

    with django_assert_num_queries(1):
        result = schema.execute_sync(
            "{ measurements { id bmr fatKg } }",
            context_value=_context(user),
        )

    assert result.errors is None
    assert len(result.data["measurements"]) == 3


@pytest.mark.django_db
def test_model_save_keeps_calculation_snapshot_consistent():
    """Direct model edits set and clear the internal snapshot consistently."""
    user = _user("model-save-snapshot@example.com")
    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20"), weight=Decimal("80")
    )
    measurement = Measurement.objects.create(
        user=user, body_fat_perc=None, weight=Decimal("75")
    )
    assert measurement.body_fat_calculation_perc == Decimal("20")

    measurement.body_fat_perc = Decimal("22")
    measurement.save(update_fields=["body_fat_perc"])
    measurement.refresh_from_db()
    assert measurement.body_fat_calculation_perc is None

    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("30"), weight=Decimal("76")
    )
    measurement.body_fat_perc = None
    measurement.save(update_fields=["body_fat_perc"])
    measurement.refresh_from_db()
    assert measurement.body_fat_calculation_perc == Decimal("20")


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
    assert measurement.body_fat_calculation_perc == Decimal("18")
    assert measurement.weight == Decimal("75.0")


@pytest.mark.django_db
def test_clearing_historical_body_fat_ignores_future_readings():
    """A historical weight can only snapshot body fat known when it was entered."""
    user = _user("historical-clear@example.com")
    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20"), weight=Decimal("80")
    )
    measurement = Measurement.objects.create(
        user=user, body_fat_perc=Decimal("25"), weight=Decimal("78")
    )
    later = Measurement.objects.create(
        user=user, body_fat_perc=Decimal("30"), weight=Decimal("76")
    )
    Measurement.objects.filter(pk__in=[measurement.pk, later.pk]).update(
        created_at=measurement.created_at
    )

    result = schema.execute_sync(
        """
            mutation ClearHistoricalBodyFat($id: ID!) {
                updateMeasurement(id: $id, weight: 78) { id }
            }
        """,
        variable_values={"id": str(measurement.id)},
        context_value=_context(user),
    )

    assert result.errors is None
    measurement.refresh_from_db()
    assert measurement.body_fat_perc is None
    assert measurement.body_fat_calculation_perc == Decimal("20")


@pytest.mark.django_db
def test_updating_weight_only_measurement_preserves_its_snapshot():
    """Editing weight later does not adopt a newer body-fat reading."""
    user = _user("update-weight-only@example.com")
    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("20"), weight=Decimal("80")
    )
    measurement = Measurement.objects.create(
        user=user, body_fat_perc=None, weight=Decimal("75")
    )
    Measurement.objects.create(
        user=user, body_fat_perc=Decimal("30"), weight=Decimal("76")
    )

    result = schema.execute_sync(
        """
            mutation UpdateWeightOnly($id: ID!) {
                updateMeasurement(id: $id, weight: 74) { id }
            }
        """,
        variable_values={"id": str(measurement.id)},
        context_value=_context(user),
    )

    assert result.errors is None
    measurement.refresh_from_db()
    assert measurement.body_fat_perc is None
    assert measurement.body_fat_calculation_perc == Decimal("20")
    assert measurement.weight == Decimal("74.0")
