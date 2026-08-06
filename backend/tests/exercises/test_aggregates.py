"""Exercise aggregate and cascade-lock regression tests."""

from decimal import Decimal

from django.contrib import admin
from django.db.models.query import QuerySet

from apps.exercises.models import Exercise
from apps.plans.models import WeekPlan


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
