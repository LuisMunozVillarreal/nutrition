"""Transactional intake aggregate regression tests."""

# pylint: disable=missing-any-param-doc,missing-return-doc
# pylint: disable=missing-return-type-doc,protected-access

from decimal import Decimal

import pytest
from django.db.models.query import QuerySet

from apps.plans.models import Day, Intake, WeekPlan


def _create_custom_intake(day, energy: str, protein: str = "0") -> Intake:
    """Create a processed custom intake with concise defaults."""
    return Intake.objects.create(
        day=day,
        food=None,
        meal=Intake.MEAL_LUNCH,
        energy_kcal=Decimal(energy),
        protein_g=Decimal(protein),
    )


def test_create_recomputes_day_nutrients_from_persisted_intakes(day):
    """A stale caller-side day cache cannot corrupt a create rollup."""
    day.energy_kcal = Decimal("900")
    day.protein_g = Decimal("90")

    _create_custom_intake(day, "100", "10")

    day.refresh_from_db()
    assert day.energy_kcal == Decimal("100.00")
    assert day.protein_g == Decimal("10.00")
    assert day.plan.energy_kcal == Decimal("100.00")


def test_update_recomputes_day_nutrients_from_persisted_intakes(day):
    """A stale cached day cannot corrupt an update rollup."""
    intake = _create_custom_intake(day, "100", "10")
    _create_custom_intake(day, "200", "20")
    intake.day.energy_kcal = Decimal("900")
    intake.day.protein_g = Decimal("90")

    intake.energy_kcal = Decimal("150")
    intake.protein_g = Decimal("15")
    intake.save()

    day.refresh_from_db()
    assert day.energy_kcal == Decimal("350.00")
    assert day.protein_g == Decimal("35.00")
    assert day.plan.energy_kcal == Decimal("350.00")


def test_delete_recomputes_day_nutrients_from_remaining_intakes(day):
    """A stale cached day cannot corrupt a delete rollup."""
    intake = _create_custom_intake(day, "100", "10")
    _create_custom_intake(day, "200", "20")
    intake.day.energy_kcal = Decimal("900")
    intake.day.protein_g = Decimal("90")

    intake.delete()

    day.refresh_from_db()
    assert day.energy_kcal == Decimal("200.00")
    assert day.protein_g == Decimal("20.00")
    assert day.plan.energy_kcal == Decimal("200.00")


def test_update_locks_plan_then_day_then_intake_once(mocker, day):
    """Existing writes lock each aggregate row once in canonical order."""
    intake = _create_custom_intake(day, "100")
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)
    intake.energy_kcal = Decimal("150")

    intake.save()

    assert locked_models == [WeekPlan, Day, Intake]


def test_day_update_locks_plan_before_day_once(mocker, day):
    """Direct day writes cannot invert the plan/day aggregate lock order."""
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)
    day.tracked = False

    day.save()

    assert locked_models == [WeekPlan, Day]


def test_create_locks_plan_then_day_once(mocker, day):
    """An intake create locks its plan before its day."""
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    _create_custom_intake(day, "100")

    assert locked_models == [WeekPlan, Day]


def test_cascade_delete_locks_plan_then_day_then_intake_once(mocker, day):
    """QuerySet/cascade deletion uses the same canonical lock order."""
    intake = _create_custom_intake(day, "100")
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    Intake.objects.filter(pk=intake.pk).delete()

    assert locked_models == [WeekPlan, Day, Intake]


def test_move_locks_both_days_by_pk_and_recomputes_both(mocker, day):
    """Moving an intake locks sorted affected days and refreshes both totals."""
    intake = _create_custom_intake(day, "100")
    destination = day.plan.days.exclude(pk=day.pk).order_by("pk").first()
    assert destination is not None
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        original_fetch_all(queryset)
        if queryset.query.select_for_update:
            locked_rows.append(
                (
                    queryset.model,
                    tuple(row.pk for row in queryset._result_cache or ()),
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)
    intake.day = destination

    intake.save()

    assert locked_rows == [
        (WeekPlan, (day.plan_id,)),
        (Day, tuple(sorted((day.pk, destination.pk)))),
        (Intake, (intake.pk,)),
    ]
    day.refresh_from_db()
    destination.refresh_from_db()
    assert day.energy_kcal == Decimal("0.00")
    assert destination.energy_kcal == Decimal("100.00")


def test_stale_update_cannot_resurrect_a_deleted_intake(day):
    """The update side of an update/delete race fails after deletion wins."""
    stale = _create_custom_intake(day, "100")
    Intake.objects.filter(pk=stale.pk).delete()
    stale.energy_kcal = Decimal("200")

    with pytest.raises(Intake.DoesNotExist):
        stale.save()

    assert not Intake.objects.filter(pk=stale.pk).exists()
    day.refresh_from_db()
    assert day.energy_kcal == Decimal("0.00")


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_intake_write_rolls_back_when_aggregate_recalculation_fails(
    mocker, day, operation
):
    """The intake row and day aggregate commit or roll back together."""
    intake = (
        _create_custom_intake(day, "100") if operation != "create" else None
    )
    day.refresh_from_db()
    original_day_energy = day.energy_kcal
    original_intakes = list(
        Intake.objects.filter(day=day).values_list("pk", "energy_kcal")
    )
    mocker.patch(
        "apps.plans.signals.handlers._recalculate_intake_days",
        side_effect=RuntimeError("injected aggregate failure"),
    )

    with pytest.raises(RuntimeError, match="injected aggregate failure"):
        if operation == "create":
            _create_custom_intake(day, "200")
        elif operation == "update":
            assert intake is not None
            intake.energy_kcal = Decimal("200")
            intake.save()
        else:
            assert intake is not None
            intake.delete()

    day.refresh_from_db()
    assert day.energy_kcal == original_day_energy
    assert (
        list(Intake.objects.filter(day=day).values_list("pk", "energy_kcal"))
        == original_intakes
    )
