"""Transactional intake aggregate regression tests."""

# pylint: disable=too-many-locals,import-outside-toplevel
# pylint: disable=too-many-arguments,too-many-positional-arguments

# pylint: disable=missing-any-param-doc,missing-return-doc
# pylint: disable=missing-return-type-doc,protected-access

from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.db import transaction
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


def test_intake_instance_delete_locks_complete_hierarchy_once(mocker, day):
    """Direct model deletion follows the same global lock hierarchy once."""
    intake = _create_custom_intake(day, "100")
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    intake.delete()

    assert locked_models == [WeekPlan, Day, Intake]


def test_admin_bulk_delete_locks_complete_hierarchy_globally_once(
    mocker, day_factory
):
    """Django admin's delete-selected path delegates to the safe queryset."""
    days = sorted((day_factory(), day_factory()), key=lambda row: row.pk)
    intakes = [
        _create_custom_intake(days[1], "200"),
        _create_custom_intake(days[0], "100"),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)
    model_admin = admin.site._registry[
        Intake
    ]  # pylint: disable=protected-access
    queryset = Intake.objects.filter(pk__in=[row.pk for row in intakes])

    model_admin.delete_queryset(None, queryset)

    assert locked_rows == [
        (WeekPlan, sorted(day.plan_id for day in days)),
        (Day, [day.pk for day in days]),
        (Intake, sorted(row.pk for row in intakes)),
    ]


def test_bulk_delete_locks_complete_hierarchy_by_pk_before_signals(
    mocker, day_factory
):
    """Interleaved intake IDs cannot invert plan/day lock acquisition."""
    days = sorted((day_factory(), day_factory()), key=lambda row: row.pk)
    remaining = [_create_custom_intake(day, "10") for day in days]
    # Deliberately assign the lower Intake PK to the higher Day/WeekPlan PK.
    deleted = [
        _create_custom_intake(days[1], "200"),
        _create_custom_intake(days[0], "100"),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    Intake.objects.filter(pk__in=[row.pk for row in deleted]).order_by(
        "-pk"
    ).delete()

    assert locked_rows == [
        (WeekPlan, sorted(day.plan_id for day in days)),
        (Day, [day.pk for day in days]),
        (Intake, sorted(row.pk for row in deleted)),
    ]
    assert list(
        Intake.objects.filter(pk__in=[row.pk for row in remaining])
        .order_by("pk")
        .values_list("energy_kcal", flat=True)
    ) == [Decimal("10.00"), Decimal("10.00")]
    for day in days:
        day.refresh_from_db()
        assert day.energy_kcal == Decimal("10.00")
        assert day.plan.energy_kcal == Decimal("10.00")


def test_day_queryset_cascade_prelocks_all_intake_hierarchies(
    mocker, day_factory
):
    """Deleting days cannot collect interleaved intakes before global locks."""
    days = sorted((day_factory(), day_factory()), key=lambda row: row.pk)
    intakes = [
        _create_custom_intake(days[1], "200"),
        _create_custom_intake(days[0], "100"),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    Day.objects.filter(pk__in=[row.pk for row in days]).order_by(
        "-pk"
    ).delete()

    assert locked_rows == [
        (WeekPlan, sorted(day.plan_id for day in days)),
        (Day, [day.pk for day in days]),
        (Intake, sorted(row.pk for row in intakes)),
    ]
    assert not Intake.objects.filter(
        pk__in=[row.pk for row in intakes]
    ).exists()


def test_day_instance_cascade_prelocks_all_intakes(mocker, day_factory):
    """A direct Day delete uses the same pre-collector lock coordinator."""
    day = day_factory()
    intakes = [
        _create_custom_intake(day, "100"),
        _create_custom_intake(day, "200"),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    day_id = day.pk
    plan_id = day.plan_id
    intake_ids = [row.pk for row in intakes]
    day.delete()

    assert locked_rows == [
        (WeekPlan, [plan_id]),
        (Day, [day_id]),
        (Intake, intake_ids),
    ]


def test_week_plan_queryset_cascade_prelocks_all_intake_hierarchies(
    mocker, day_factory
):
    """Deleting plans locks all cascaded intake rows before collection."""
    days = sorted((day_factory(), day_factory()), key=lambda row: row.plan_id)
    intakes = [
        _create_custom_intake(days[1], "200"),
        _create_custom_intake(days[0], "100"),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    WeekPlan.objects.filter(pk__in=[row.plan_id for row in days]).order_by(
        "-pk"
    ).delete()

    assert locked_rows == [
        (WeekPlan, sorted(day.plan_id for day in days)),
        (Day, sorted(day.pk for day in days)),
        (Intake, sorted(row.pk for row in intakes)),
    ]
    assert not Intake.objects.filter(
        pk__in=[row.pk for row in intakes]
    ).exists()


def test_week_plan_instance_cascade_prelocks_all_intake_hierarchies(
    mocker, day_factory
):
    """Direct WeekPlan deletion uses one global pre-collector lock pass."""
    day = day_factory()
    plan = day.plan
    plan_id = plan.pk
    other_day = plan.days.exclude(pk=day.pk).order_by("pk").first()
    assert other_day is not None
    intakes = [
        _create_custom_intake(other_day, "200"),
        _create_custom_intake(day, "100"),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (queryset.model, [row.pk for row in queryset._result_cache])
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    plan.delete()

    deduped_locked_rows = []
    seen: set[tuple[type, tuple[int, ...]]] = set()
    for model, row_ids in locked_rows:
        if not row_ids:
            continue
        normalized_ids = tuple(row_ids)
        marker = (model, normalized_ids)
        if marker in seen:
            continue
        seen.add(marker)
        deduped_locked_rows.append((model, list(normalized_ids)))

    assert deduped_locked_rows == [
        (WeekPlan, [plan_id]),
        (Day, sorted((day.pk, other_day.pk))),
        (Intake, sorted(row.pk for row in intakes)),
    ]


@pytest.mark.parametrize("root_model", [Day, WeekPlan])
def test_instance_cascade_discovers_targets_inside_atomic_block(
    mocker, day, root_model
):
    """Direct cascade target discovery must run inside the delete transaction."""
    _create_custom_intake(day, "100")
    from apps.plans.models import intake as intake_module

    original_targets = intake_module.intake_targets_for_cascade
    observed_atomic: list[bool] = []

    def assert_atomic(targets, using):
        observed_atomic.append(
            transaction.get_connection(using).in_atomic_block
        )
        return original_targets(targets, using)

    mocker.patch.object(
        intake_module,
        "intake_targets_for_cascade",
        side_effect=assert_atomic,
    )

    root = day if root_model is Day else day.plan
    root.delete()

    assert observed_atomic
    assert all(observed_atomic)


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


def test_cascade_queryset_without_rows_uses_normal_delete(mocker):
    """Cascade roots skip locking when the intake query resolves empty rows."""
    from apps.plans.models.intake import IntakeCascadeQuerySet

    queryset = IntakeCascadeQuerySet(model=Day, using="default")
    targets = mocker.Mock()
    targets.exists.return_value = True
    targets.order_by.return_value.values_list.return_value.distinct.return_value = ()
    mocker.patch(
        "apps.plans.models.intake.intake_targets_for_cascade",
        return_value=targets,
    )
    normal_delete = mocker.patch.object(
        QuerySet, "delete", return_value=(1, {"plans.Day": 1})
    )

    assert queryset.delete() == (1, {"plans.Day": 1})
    normal_delete.assert_called_once_with()


def test_cascade_queryset_reuses_covering_locks_without_recompute_bundle(
    mocker,
):
    """Existing deletion locks may cover rows without aggregate recompute."""
    from apps.plans.models.intake import IntakeCascadeQuerySet

    queryset = IntakeCascadeQuerySet(model=Day, using="default")
    targets = mocker.Mock()
    targets.exists.return_value = True
    targets.order_by.return_value.values_list.return_value.distinct.return_value = (
        (8, 3),
    )
    mocker.patch(
        "apps.plans.models.intake.intake_targets_for_cascade",
        return_value=targets,
    )
    mocker.patch(
        "apps.plans.models.intake.get_intake_deletion_locks",
        return_value=SimpleNamespace(
            covers=lambda *_args, **_kwargs: True,
            aggregate_locks=None,
        ),
    )
    normal_delete = mocker.patch.object(
        QuerySet, "delete", return_value=(1, {"plans.Day": 1})
    )

    assert queryset.delete() == (1, {"plans.Day": 1})
    normal_delete.assert_called_once_with()


@pytest.mark.parametrize(
    ("intake_exists", "exercise_exists", "intake_locked", "exercise_locked"),
    [
        (True, True, True, True),
        (False, False, False, False),
        (True, False, False, False),
    ],
)
def test_day_instance_cascade_delete_handles_combined_and_empty_lock_sets(
    mocker,
    day,
    intake_exists,
    exercise_exists,
    intake_locked,
    exercise_locked,
):
    """Direct root deletion supports both dual-lock and lock-free cascades."""
    target_qs = SimpleNamespace(
        delete=mocker.Mock(return_value=(1, {"plans.Day": 1}))
    )
    manager = SimpleNamespace(
        using=lambda _using: SimpleNamespace(
            filter=lambda **_kwargs: target_qs
        )
    )
    mocker.patch.object(Day, "objects", manager)
    intake_targets = mocker.Mock()
    intake_targets.exists.return_value = intake_exists
    intake_targets.order_by.return_value.values_list.return_value = [day.pk]
    exercise_targets = mocker.Mock()
    exercise_targets.exists.return_value = exercise_exists
    exercise_targets.order_by.return_value.values_list.return_value = [day.pk]
    mocker.patch(
        "apps.plans.models.intake.intake_targets_for_cascade",
        return_value=intake_targets,
    )
    mocker.patch(
        "apps.exercises.models.exercise_targets_for_cascade",
        return_value=exercise_targets,
    )
    aggregate_locks = SimpleNamespace(clear_markers=mocker.Mock())
    lock_plan = mocker.patch(
        "apps.plans.models.intake.lock_plan_aggregate_rows",
        return_value=aggregate_locks,
    )
    mocker.patch(
        "apps.plans.models.intake.lock_intake_deletion_rows",
        return_value=object() if intake_locked else None,
    )
    mocker.patch(
        "apps.exercises.models.lock_exercise_deletion_rows",
        return_value=object() if exercise_locked else None,
    )
    mocker.patch(
        "apps.plans.models.intake.activate_intake_deletion_locks",
        side_effect=lambda _locks: nullcontext(),
    )
    mocker.patch(
        "apps.exercises.models.activate_exercise_deletion_locks",
        side_effect=lambda _locks: nullcontext(),
    )

    result = day.delete()

    assert result == (1, {"plans.Day": 1})
    if intake_exists or exercise_exists:
        lock_plan.assert_called_once_with(using="default", day_ids=(day.pk,))
        aggregate_locks.clear_markers.assert_called_once_with()
    else:
        lock_plan.assert_not_called()
