"""Exercise aggregate and cascade-lock regression tests."""

# pylint: disable=protected-access

from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.db import models
from django.db.models.query import QuerySet

from apps.exercises.models import (
    Exercise,
    ExerciseDeletionLocks,
    ExerciseQuerySet,
    _ExerciseOwnerChanged,
    exercise_targets_for_cascade,
    lock_exercise_deletion_rows,
)
from apps.plans.models import Day, WeekPlan


def _dedupe_lock_rows(
    rows: list[tuple[type, list[int]]],
) -> list[tuple[type, list[int]]]:
    merged: dict[type, set[int]] = {}
    order: list[type] = []

    for model, row_pks in rows:
        safe_pks = {row_pk for row_pk in row_pks if isinstance(row_pk, int)}
        if model not in order:
            order.append(model)
            merged[model] = safe_pks
            continue
        merged[model].update(safe_pks)

    return [(model, sorted(merged[model])) for model in order]


def _create_custom_exercise(day) -> Exercise:
    """Create a deterministic exercise row."""
    return Exercise.objects.create(
        day=day,
        time="10:00",
        type=Exercise.EXERCISE_CYCLE,
        kcals=100,
        distance=Decimal("1.20"),
    )


def test_exercise_instance_delete_locks_complete_hierarchy_once(mocker, day):
    """Deleting one exercise should lock plan then day then exercise."""
    exercise = _create_custom_exercise(day)
    exercise_day_pk = exercise.day_id
    exercise_plan_pk = day.plan_id
    locked_models = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        if queryset.query.select_for_update:
            locked_models.append(queryset.model)
        return original_fetch_all(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    exercise.delete()

    deduped_models = list(dict.fromkeys(locked_models).keys())

    assert deduped_models == [WeekPlan, type(day), Exercise]
    assert exercise_plan_pk is not None
    assert exercise_day_pk == day.pk


def test_exercise_queryset_delete_locks_complete_hierarchy_once(
    mocker, exercise
):
    """Queryset deletion should use the same hierarchy for an exercise."""
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (
                    queryset.model,
                    [row.pk for row in queryset._result_cache],
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    Exercise.objects.filter(pk=exercise.pk).delete()

    assert _dedupe_lock_rows(locked_rows) == [
        (WeekPlan, [exercise.day.plan_id]),
        (type(exercise.day), [exercise.day_id]),
        (Exercise, [exercise.pk]),
    ]


def test_exercise_admin_bulk_delete_locks_complete_hierarchy_globally_once(
    mocker, day_factory
):
    """Admin bulk delete should delegate to the same safe QuerySet flow."""
    days = sorted((day_factory(), day_factory()), key=lambda row: row.pk)
    exercises = [
        _create_custom_exercise(days[1]),
        _create_custom_exercise(days[0]),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (
                    queryset.model,
                    [row.pk for row in queryset._result_cache],
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)
    model_admin = admin.site._registry[
        Exercise
    ]  # pylint: disable=protected-access
    queryset = Exercise.objects.filter(pk__in=[row.pk for row in exercises])

    model_admin.delete_queryset(None, queryset)

    assert _dedupe_lock_rows(locked_rows) == [
        (WeekPlan, sorted(day.plan_id for day in days)),
        (type(days[0]), sorted(day.pk for day in days)),
        (Exercise, sorted(row.pk for row in exercises)),
    ]


def test_exercise_day_cascade_delete_locks_complete_hierarchy_by_cascade(
    mocker, day
):
    """Deleting a Day should pre-lock all cascaded exercises in hierarchy."""
    first = _create_custom_exercise(day)
    second = _create_custom_exercise(day)
    exercise_ids = [first.pk, second.pk]
    day_id = day.pk
    day_pk = day.pk
    exercise_plan_pk = day.plan_id
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (
                    queryset.model,
                    [row.pk for row in queryset._result_cache],
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    day.delete()

    merged_locked_rows = _dedupe_lock_rows(locked_rows)

    day_type = type(day)
    assert day_pk is not None

    normalized_compact_rows = [
        (model, [day_pk] if model is day_type else row_pks)
        for model, row_pks in merged_locked_rows
    ]

    assert normalized_compact_rows == [
        (WeekPlan, [exercise_plan_pk]),
        (day_type, [day_id]),
        (Exercise, sorted(exercise_ids)),
    ]


def test_exercise_deletion_lock_helpers_cover_mismatch_paths(mocker):
    """Deletion lock helpers fail closed for mismatches and missing days."""
    saved_day = SimpleNamespace(save=mocker.Mock())
    aggregate_locks = SimpleNamespace(
        days_by_pk={2: saved_day},
        clear_markers=mocker.Mock(),
    )
    locks = ExerciseDeletionLocks(
        using="default",
        aggregate_locks=aggregate_locks,
        exercises=(SimpleNamespace(pk=1),),
    )

    assert not locks.covers(1, "replica", 2)
    assert not locks.covers(2, "default", 2)
    assert not ExerciseDeletionLocks(
        using="default",
        aggregate_locks=None,
        exercises=(),
    ).covers(1, "default", None)

    locks.recompute_days({2, 99}, using="default")
    locks.clear_markers()
    ExerciseDeletionLocks(
        using="default",
        aggregate_locks=None,
        exercises=(),
    ).recompute_days({2}, using="default")
    ExerciseDeletionLocks(
        using="default",
        aggregate_locks=None,
        exercises=(),
    ).clear_markers()

    saved_day.save.assert_called_once_with(using="default")
    aggregate_locks.clear_markers.assert_called_once_with()


def test_lock_exercise_deletion_rows_handles_empty_and_prelocked_targets(
    mocker,
):
    """Deletion-row discovery handles empty selections and supplied locks."""
    empty_targets = mocker.Mock()
    empty_targets.values_list.return_value = []

    empty_locks = lock_exercise_deletion_rows(empty_targets, "default")

    assert empty_locks.aggregate_locks is None
    assert not empty_locks.exercises

    manager = mocker.Mock()
    manager.using.return_value.filter.return_value.values_list.return_value = [
        3
    ]
    locked_queryset = manager.select_for_update.return_value.using.return_value
    locked_queryset.filter.return_value.order_by.return_value = [
        SimpleNamespace(pk=7, day_id=3)
    ]
    mocker.patch("apps.exercises.models.apps.get_model").return_value = (
        SimpleNamespace(objects=manager)
    )
    targets = mocker.Mock()
    targets.values_list.return_value = [7]
    locked_day = SimpleNamespace(pk=3)
    aggregate_locks = SimpleNamespace(days_by_pk={3: locked_day})

    locks = lock_exercise_deletion_rows(
        targets,
        "default",
        aggregate_locks=aggregate_locks,
    )

    assert locks.aggregate_locks is aggregate_locks
    assert [exercise.pk for exercise in locks.exercises] == [7]
    assert locks.exercises[0].day is locked_day


def test_exercise_targets_for_unrelated_cascade_is_empty(mocker):
    """Only day and week-plan cascades select exercise rows."""
    targets = SimpleNamespace(
        model=SimpleNamespace(_meta=SimpleNamespace(label_lower="plans.other"))
    )
    manager = mocker.Mock()
    empty = manager.using.return_value.none.return_value
    mocker.patch("apps.exercises.models.apps.get_model").return_value = (
        SimpleNamespace(objects=manager)
    )

    assert exercise_targets_for_cascade(targets, "default") is empty
    manager.using.return_value.none.assert_called_once_with()


def test_queryset_delete_reuses_covering_locks_and_recomputes_once(mocker):
    """Covered queryset deletes skip relocking and recompute once."""
    queryset = ExerciseQuerySet(model=Exercise, using="default")
    queryset._db = "default"
    queryset.order_by = mocker.Mock(
        return_value=SimpleNamespace(
            values_list=mocker.Mock(
                return_value=SimpleNamespace(
                    distinct=mocker.Mock(return_value=[1])
                )
            )
        )
    )
    queryset.model = SimpleNamespace(
        objects=SimpleNamespace(
            using=lambda _using: SimpleNamespace(
                filter=lambda **_kwargs: SimpleNamespace(
                    values_list=lambda *_args, **_kwargs2: SimpleNamespace(
                        first=lambda: 5
                    )
                )
            )
        )
    )
    aggregate_locks = SimpleNamespace(
        days_by_pk={5: object()},
        recompute_days=mocker.Mock(),
    )
    existing = SimpleNamespace(
        aggregate_locks=aggregate_locks,
        covers=mocker.Mock(return_value=True),
    )
    mocker.patch(
        "apps.exercises.models.get_exercise_deletion_locks",
        return_value=existing,
    )
    normal_delete = mocker.patch.object(
        models.QuerySet, "delete", return_value=(1, {"exercises.Exercise": 1})
    )

    assert queryset.delete() == (1, {"exercises.Exercise": 1})

    normal_delete.assert_called_once_with()
    aggregate_locks.recompute_days.assert_called_once_with(
        {5}, using="default"
    )


def test_queryset_delete_relocks_when_existing_bundle_misses_target(mocker):
    """Any uncovered exercise falls back to the canonical relock path."""
    queryset = ExerciseQuerySet(model=Exercise, using="default")
    queryset._db = "default"
    queryset.order_by = mocker.Mock(
        return_value=SimpleNamespace(
            values_list=mocker.Mock(
                return_value=SimpleNamespace(
                    distinct=mocker.Mock(return_value=[1])
                )
            )
        )
    )
    queryset.model = SimpleNamespace(
        objects=SimpleNamespace(
            using=lambda _using: SimpleNamespace(
                filter=lambda **_kwargs: SimpleNamespace(
                    values_list=lambda *_args, **_kwargs2: SimpleNamespace(
                        first=lambda: 5
                    )
                )
            )
        )
    )
    existing = SimpleNamespace(
        aggregate_locks=SimpleNamespace(days_by_pk={5: object()}),
        covers=mocker.Mock(return_value=False),
    )
    fresh_locks = SimpleNamespace(
        aggregate_locks=SimpleNamespace(days_by_pk={5: object()}),
        recompute_days=mocker.Mock(),
        clear_markers=mocker.Mock(),
    )
    mocker.patch(
        "apps.exercises.models.get_exercise_deletion_locks",
        return_value=existing,
    )
    mocker.patch(
        "apps.exercises.models.lock_exercise_deletion_rows",
        return_value=fresh_locks,
    )
    mocker.patch(
        "apps.exercises.models.activate_exercise_deletion_locks",
        side_effect=lambda _locks: nullcontext(),
    )
    normal_delete = mocker.patch.object(
        models.QuerySet, "delete", return_value=(1, {"exercises.Exercise": 1})
    )

    assert queryset.delete() == (1, {"exercises.Exercise": 1})

    normal_delete.assert_called_once_with()
    fresh_locks.recompute_days.assert_called_once_with({5}, using="default")
    fresh_locks.clear_markers.assert_called_once_with()


def test_queryset_delete_allows_empty_aggregate_lock_bundle(mocker):
    """Deleting an empty selection skips aggregate recomputation safely."""
    queryset = ExerciseQuerySet(model=Exercise, using="default")
    queryset._db = "default"
    locks = ExerciseDeletionLocks(
        using="default",
        aggregate_locks=None,
        exercises=(),
    )
    mocker.patch(
        "apps.exercises.models.get_exercise_deletion_locks",
        return_value=None,
    )
    mocker.patch(
        "apps.exercises.models.lock_exercise_deletion_rows",
        return_value=locks,
    )
    mocker.patch(
        "apps.exercises.models.activate_exercise_deletion_locks",
        side_effect=lambda _locks: nullcontext(),
    )
    normal_delete = mocker.patch.object(
        models.QuerySet,
        "delete",
        return_value=(0, {}),
    )

    assert queryset.delete() == (0, {})
    normal_delete.assert_called_once_with()


def test_lock_write_rows_raises_when_persisted_row_disappears(mocker):
    """Updates fail clearly when the target row vanishes before locking."""
    exercise = Exercise(day_id=3, type=Exercise.EXERCISE_WALK, kcals=10)
    exercise.pk = 11
    exercise._state.adding = False
    manager = mocker.Mock()
    lookup = (
        manager.using.return_value.filter.return_value.values_list.return_value
    )
    lookup.first.return_value = None
    mocker.patch.object(Exercise, "objects", manager)
    mocker.patch(
        "apps.exercises.models.lock_plan_aggregate_rows",
        return_value=SimpleNamespace(
            days_by_pk={3: Day(pk=3)},
            clear_markers=mocker.Mock(),
        ),
    )

    with pytest.raises(Exercise.DoesNotExist):
        exercise._lock_write_rows("default")


def test_lock_write_rows_raises_when_owner_changes_after_lock(mocker):
    """A stale owner snapshot triggers the bounded save retry."""
    exercise = Exercise(day_id=3, type=Exercise.EXERCISE_WALK, kcals=10)
    exercise.pk = 11
    exercise._caller_day = SimpleNamespace()
    manager = mocker.Mock()
    lookup = (
        manager.using.return_value.filter.return_value.values_list.return_value
    )
    lookup.first.return_value = 3
    locked_get = manager.select_for_update.return_value.using.return_value.get
    locked_get.return_value = SimpleNamespace(day_id=4)
    mocker.patch.object(Exercise, "objects", manager)
    locked_day = Day(pk=3)
    mocker.patch(
        "apps.exercises.models.lock_plan_aggregate_rows",
        return_value=SimpleNamespace(
            days_by_pk={3: locked_day, 4: Day(pk=4)},
            clear_markers=mocker.Mock(),
        ),
    )

    with pytest.raises(_ExerciseOwnerChanged):
        exercise._lock_write_rows("default")

    assert exercise.day is locked_day


def test_recompute_touched_days_skips_when_no_locks(day):
    """No-op recomputation is allowed when no aggregate locks were set."""
    exercise = Exercise(day=day, type=Exercise.EXERCISE_WALK, kcals=10)

    exercise._recompute_touched_days("default", previous_day_id=day.pk)
    exercise._clear_write_locks()


def test_save_retries_owner_change_once_without_outer_transaction(mocker, day):
    """A top-level save retries one owner-change race before succeeding."""
    exercise = Exercise(day=day, type=Exercise.EXERCISE_WALK, kcals=10)
    exercise._caller_day = None
    mocker.patch(
        "apps.exercises.models.transaction.get_connection",
        return_value=SimpleNamespace(in_atomic_block=False),
    )
    mocker.patch(
        "apps.exercises.models.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    lock_rows = mocker.patch.object(
        Exercise,
        "_lock_write_rows",
        side_effect=[_ExerciseOwnerChanged, None],
    )
    model_save = mocker.patch.object(models.Model, "save")
    recompute = mocker.patch.object(Exercise, "_recompute_touched_days")
    cleanup = mocker.patch.object(Exercise, "_clear_write_locks")

    exercise.save(using="default")

    assert lock_rows.call_count == 2
    model_save.assert_called_once_with(using="default")
    recompute.assert_called_once_with("default", None)
    assert cleanup.call_count == 2


def test_save_surfaces_owner_changes_inside_outer_transaction(mocker, day):
    """Nested callers receive the explicit retry-required error."""
    exercise = Exercise(day=day, type=Exercise.EXERCISE_WALK, kcals=10)
    mocker.patch(
        "apps.exercises.models.transaction.get_connection",
        return_value=SimpleNamespace(in_atomic_block=True),
    )
    mocker.patch(
        "apps.exercises.models.transaction.atomic",
        side_effect=lambda **_kwargs: nullcontext(),
    )
    mocker.patch.object(
        Exercise, "_lock_write_rows", side_effect=_ExerciseOwnerChanged
    )
    cleanup = mocker.patch.object(Exercise, "_clear_write_locks")

    with pytest.raises(RuntimeError, match="owner changed"):
        exercise.save(using="default")

    cleanup.assert_called_once_with()


def test_delete_falls_back_to_model_delete_for_missing_row(mocker, day):
    """Deleting a stale instance delegates to Django's missing-row path."""
    exercise = Exercise(day=day, type=Exercise.EXERCISE_WALK, kcals=10)
    exercise.pk = 99
    manager = SimpleNamespace(
        using=lambda _using: SimpleNamespace(
            filter=lambda **_kwargs: SimpleNamespace(exists=lambda: False)
        )
    )
    mocker.patch.object(type(exercise), "objects", manager)
    model_delete = mocker.patch.object(
        models.Model,
        "delete",
        return_value=(0, {"exercises.Exercise": 0}),
    )

    assert exercise.delete() == (0, {"exercises.Exercise": 0})
    model_delete.assert_called_once_with(exercise)


def test_delete_reuses_covering_deletion_locks(mocker, day):
    """Instance delete avoids relocking inside a covered lock bundle."""
    exercise = _create_custom_exercise(day)
    manager = SimpleNamespace(
        using=lambda _using: SimpleNamespace(
            filter=lambda **_kwargs: SimpleNamespace(
                exists=lambda: True,
                delete=lambda: (1, {"exercises.Exercise": 1}),
            )
        )
    )
    mocker.patch.object(Exercise, "objects", manager)
    mocker.patch(
        "apps.exercises.models.get_exercise_deletion_locks",
        return_value=SimpleNamespace(covers=lambda *_args: True),
    )
    relock = mocker.patch("apps.exercises.models.lock_exercise_deletion_rows")

    assert exercise.delete() == (1, {"exercises.Exercise": 1})
    relock.assert_not_called()


def test_delete_preserves_lock_acquisition_error(mocker, day):
    """A lock acquisition failure must not be masked by cleanup."""
    exercise = _create_custom_exercise(day)
    targets = SimpleNamespace(exists=lambda: True)
    manager = SimpleNamespace(
        using=lambda _using: SimpleNamespace(
            filter=lambda **_kwargs: targets,
        )
    )
    mocker.patch.object(Exercise, "objects", manager)
    mocker.patch(
        "apps.exercises.models.get_exercise_deletion_locks",
        return_value=None,
    )
    mocker.patch(
        "apps.exercises.models.lock_exercise_deletion_rows",
        side_effect=RuntimeError("lock acquisition failed"),
    )

    with pytest.raises(RuntimeError, match="lock acquisition failed"):
        exercise.delete(using="default")
