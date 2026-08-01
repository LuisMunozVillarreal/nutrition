"""Focused branch coverage for plan locking and intake helpers."""

# pylint: disable=protected-access

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from django.db import models

from apps.plans.locks import PlanAggregateLocks
from apps.plans.models import Day, Intake
from apps.plans.models.intake import (
    IntakeCascadeQuerySet,
    _IntakeOwnerChanged,
    intake_targets_for_cascade,
)
from apps.plans.signals.handlers import (
    _recalculate_intake_days,
    lock_day_and_intake_before_delete,
)


def test_clear_markers_ignores_days_owned_by_another_lock_set():
    """Clearing one lock set never removes another set's marker."""
    other_locks = object()
    owned_elsewhere = SimpleNamespace(pk=1, _plan_aggregate_locks=other_locks)
    unmarked = SimpleNamespace(pk=2)
    locks = PlanAggregateLocks(
        using="default", plans=(), days=(owned_elsewhere, unmarked)
    )

    locks.clear_markers()

    assert owned_elsewhere._plan_aggregate_locks is other_locks
    assert not hasattr(unmarked, "_plan_aggregate_locks")


def test_intake_targets_for_unrelated_cascade_is_empty(mocker):
    """Only day and week-plan cascades select intake rows."""
    targets = SimpleNamespace(
        model=SimpleNamespace(_meta=SimpleNamespace(label_lower="plans.other"))
    )
    manager = mocker.Mock()
    using = manager.using.return_value
    empty = using.none.return_value
    mocker.patch("apps.plans.models.intake.apps.get_model").return_value = (
        SimpleNamespace(objects=manager)
    )

    assert intake_targets_for_cascade(targets, "default") is empty
    using.none.assert_called_once_with()


def test_cascade_queryset_without_intakes_uses_normal_delete(mocker):
    """Root deletion skips intake locking when no intakes can cascade."""
    queryset = IntakeCascadeQuerySet(model=Day, using="default")
    targets = mocker.Mock()
    targets.exists.return_value = False
    mocker.patch(
        "apps.plans.models.intake.intake_targets_for_cascade",
        return_value=targets,
    )
    normal_delete = mocker.patch.object(
        models.QuerySet, "delete", return_value=(1, {"plans.Day": 1})
    )

    assert queryset.delete() == (1, {"plans.Day": 1})
    normal_delete.assert_called_once_with()


def test_clear_write_locks_handles_present_and_absent_markers(mocker):
    """Intake cleanup clears live markers and remains idempotent."""
    intake = Intake()
    locks = mocker.Mock()
    intake._nutrition_locks = locks
    intake._nutrition_day_ids = (1,)

    intake._clear_write_locks()
    intake._clear_write_locks()

    locks.clear_markers.assert_called_once_with()
    assert intake._nutrition_locks is None
    assert not intake._nutrition_day_ids


def test_lock_write_rows_detects_a_concurrent_owner_change(mocker):
    """A stale owner lookup forces the bounded write retry path."""
    intake = Intake(day_id=1, meal="lunch", num_servings=1)
    intake.pk = 7
    intake._caller_day = SimpleNamespace(pk=1)
    lookup = mocker.Mock()
    using_manager = lookup.using.return_value
    using_manager.filter.return_value.values_list.return_value.first.return_value = (
        1
    )
    previous = SimpleNamespace(day_id=2)
    lookup.select_for_update.return_value.using.return_value.get.return_value = (
        previous
    )
    mocker.patch.object(Intake, "objects", lookup)
    locked_day = Day(pk=1)
    aggregate_locks = SimpleNamespace(
        days_by_pk={1: locked_day}, clear_markers=mocker.Mock()
    )
    mocker.patch(
        "apps.plans.models.intake.lock_plan_aggregate_rows",
        return_value=aggregate_locks,
    )

    with pytest.raises(_IntakeOwnerChanged):
        intake._lock_write_rows("default")

    assert intake.day is locked_day
    assert intake._caller_day.pk == 1


def test_save_surfaces_owner_changes_inside_outer_transactions(mocker):
    """Callers already in a transaction receive an explicit retry error."""
    intake = Intake(day_id=1, meal="lunch", num_servings=1)
    mocker.patch(
        "apps.plans.models.intake.transaction.get_connection",
        return_value=SimpleNamespace(in_atomic_block=True),
    )
    mocker.patch(
        "apps.plans.models.intake.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    mocker.patch.object(
        Intake, "_lock_write_rows", side_effect=_IntakeOwnerChanged
    )
    cleanup = mocker.patch.object(Intake, "_clear_write_locks")

    with pytest.raises(RuntimeError, match="owner changed"):
        intake.save(using="default")

    cleanup.assert_called_once_with()


def test_save_retries_owner_changes_outside_outer_transactions(mocker):
    """Standalone writes retry once after a concurrent owner change."""
    intake = Intake(day_id=1, meal="lunch", num_servings=1)
    mocker.patch(
        "apps.plans.models.intake.transaction.get_connection",
        return_value=SimpleNamespace(in_atomic_block=False),
    )
    mocker.patch(
        "apps.plans.models.intake.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    lock_write = mocker.patch.object(
        Intake,
        "_lock_write_rows",
        side_effect=[_IntakeOwnerChanged, None],
    )
    mocker.patch(
        "apps.plans.models.intake.lock_intake_cupboard_rows",
        return_value=(),
    )
    mocker.patch(
        "apps.foods.cupboard_locks.activate_cupboard_item_locks",
        side_effect=lambda _locks: nullcontext(),
    )
    persisted = mocker.patch.object(models.Model, "save")

    intake.save(using="default")

    assert lock_write.call_count == 2
    persisted.assert_called_once()


def test_recalculate_intake_days_acquires_missing_aggregate_locks(mocker):
    """Signal fallback obtains locks and persists transaction-visible totals."""
    day = SimpleNamespace(pk=3, save=mocker.Mock())
    locks = SimpleNamespace(days_by_pk={3: day})
    lock_rows = mocker.patch(
        "apps.plans.signals.handlers.lock_plan_aggregate_rows",
        return_value=locks,
    )
    totals_query = mocker.Mock()
    totals_query.filter.return_value.aggregate.return_value = {
        "energy_kcal": 12
    }
    manager = mocker.Mock()
    manager.using.return_value = totals_query
    mocker.patch.object(Intake, "objects", manager)
    instance = SimpleNamespace(day_id=3)

    _recalculate_intake_days(instance, "default")

    lock_rows.assert_called_once_with(using="default", day_ids=(3,))
    assert instance._nutrition_locks is locks
    assert day.energy_kcal == 12
    day.save.assert_called_once_with(using="default")
    assert instance.day is day


def test_delete_signal_reuses_active_deletion_locks(mocker):
    """Bulk deletion reuses its canonical lock set without relocking rows."""
    day = SimpleNamespace(pk=4)
    aggregate_locks = SimpleNamespace(
        days_by_pk={4: day}, covers_days=lambda *_args: True
    )
    deletion_locks = SimpleNamespace(
        aggregate_locks=aggregate_locks,
        covers=lambda *_args: True,
    )
    mocker.patch(
        "apps.plans.signals.handlers.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    mocker.patch(
        "apps.plans.signals.handlers.get_intake_deletion_locks",
        return_value=deletion_locks,
    )
    relock = mocker.patch(
        "apps.plans.signals.handlers.lock_plan_aggregate_rows"
    )
    instance = SimpleNamespace(pk=8, day_id=4)

    lock_day_and_intake_before_delete(Intake, instance, using="default")

    relock.assert_not_called()
    assert instance._nutrition_locks is aggregate_locks
    assert instance.day is day
    assert instance._nutrition_day_ids == (4,)


def test_delete_signal_relocks_when_active_locks_do_not_cover_day(mocker):
    """A stale marker is replaced and the intake row is locked explicitly."""
    stale = SimpleNamespace(covers_days=lambda *_args: False)
    day = SimpleNamespace(pk=5)
    fresh = SimpleNamespace(days_by_pk={5: day})
    mocker.patch(
        "apps.plans.signals.handlers.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    mocker.patch(
        "apps.plans.signals.handlers.get_intake_deletion_locks",
        return_value=None,
    )
    lock_rows = mocker.patch(
        "apps.plans.signals.handlers.lock_plan_aggregate_rows",
        return_value=fresh,
    )
    manager = mocker.Mock()
    mocker.patch.object(Intake, "objects", manager)
    instance = SimpleNamespace(pk=9, day_id=5, _nutrition_locks=stale)

    lock_day_and_intake_before_delete(Intake, instance, using="default")

    lock_rows.assert_called_once_with(using="default", day_ids=(5,))
    locked_queryset = manager.select_for_update.return_value.using.return_value
    locked_queryset.get.assert_called_once_with(pk=9)
    assert instance._nutrition_locks is fresh
    assert instance.day is day
