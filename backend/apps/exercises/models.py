"""Exercise model module."""

import datetime
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator, cast

from django.apps import apps
from django.db import models, router, transaction

from apps.libs.basemodel import BaseModel
from apps.plans.locks import PlanAggregateLocks, lock_plan_aggregate_rows

_active_exercise_deletion_locks: ContextVar["ExerciseDeletionLocks | None"] = (
    ContextVar("active_exercise_deletion_locks", default=None)
)


@dataclass
class ExerciseDeletionLocks:
    """Rows and aggregate locks held during exercise deletion."""

    using: str
    aggregate_locks: PlanAggregateLocks | None
    exercises: tuple["Exercise", ...]

    def covers(self, exercise_pk: int, using: str, day_id: int | None) -> bool:
        """Whether these locks cover a concrete exercise/day on this DB."""
        if self.using != using or self.aggregate_locks is None:
            return False
        if any(exercise.pk == exercise_pk for exercise in self.exercises):
            return day_id is None or day_id in self.aggregate_locks.days_by_pk
        return False

    def recompute_days(self, day_ids: set[int], using: str) -> None:
        """Recompute every touched day currently protected by these locks."""
        if self.aggregate_locks is None:
            return

        for day_id in sorted(day_ids):
            if day_id in self.aggregate_locks.days_by_pk:
                self.aggregate_locks.days_by_pk[day_id].save(using=using)

    def clear_markers(self) -> None:
        """Drop transaction-scoped lock markers from locked instances."""
        if self.aggregate_locks is not None:
            self.aggregate_locks.clear_markers()


class _ExerciseOwnerChanged(RuntimeError):
    """Signal that exercise owner day changed while acquiring locks."""


_ExerciseLocks = tuple[str, int] | tuple[()]


def get_exercise_deletion_locks() -> ExerciseDeletionLocks | None:
    """Return active exercise deletion locks for signal handlers."""
    return _active_exercise_deletion_locks.get()


@contextmanager
def activate_exercise_deletion_locks(
    locks: ExerciseDeletionLocks,
) -> Iterator[None]:
    """Expose exercise deletion locks to signal handlers."""
    token = _active_exercise_deletion_locks.set(locks)
    try:
        yield
    finally:
        _active_exercise_deletion_locks.reset(token)


def lock_exercise_deletion_rows(
    targets,
    using: str,
    aggregate_locks: PlanAggregateLocks | None = None,
) -> ExerciseDeletionLocks:
    """Lock exercises and all impacted days before delete collector runs."""
    exercise_model = apps.get_model("exercises", "Exercise")
    exercise_ids = tuple(sorted(targets.values_list("pk", flat=True)))
    if not exercise_ids:
        return ExerciseDeletionLocks(
            using=using,
            aggregate_locks=None,
            exercises=tuple(),
        )

    day_ids = tuple(
        sorted(
            {
                day_id
                for day_id in exercise_model.objects.using(using)
                .filter(pk__in=exercise_ids)
                .values_list("day_id", flat=True)
                if day_id is not None
            }
        )
    )

    resolved_aggregate_locks = aggregate_locks
    if resolved_aggregate_locks is None and day_ids:
        resolved_aggregate_locks = lock_plan_aggregate_rows(
            using=using,
            day_ids=day_ids,
        )

    exercises = tuple(
        exercise
        for exercise in exercise_model.objects.select_for_update(of=("self",))
        .using(using)
        .filter(pk__in=exercise_ids)
        .order_by("pk")
    )
    if resolved_aggregate_locks is not None:
        for exercise in exercises:
            if exercise.day_id is not None:
                exercise.day = resolved_aggregate_locks.days_by_pk[
                    exercise.day_id
                ]

    return ExerciseDeletionLocks(
        using=using,
        aggregate_locks=resolved_aggregate_locks,
        exercises=exercises,
    )


def exercise_targets_for_cascade(
    targets: models.QuerySet,
    using: str,
) -> models.QuerySet:
    """Return exercises cascaded through a Day or WeekPlan deletion."""
    exercise_model = cast(
        type["Exercise"], apps.get_model("exercises", "Exercise")
    )
    target_label = targets.model._meta.label_lower

    if target_label == "plans.day":
        return exercise_model.objects.using(using).filter(
            day_id__in=targets.order_by().values("pk")
        )
    if target_label == "plans.weekplan":
        return exercise_model.objects.using(using).filter(
            day__plan_id__in=targets.order_by().values("pk")
        )

    return exercise_model.objects.using(using).none()


class ExerciseQuerySet(models.QuerySet):
    """QuerySet that deletes exercises under canonical aggregate locks."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Delete selected exercises under aggregate locks."""
        using = self.db
        existing_locks = get_exercise_deletion_locks()
        if (
            existing_locks is not None
            and existing_locks.aggregate_locks is not None
        ):
            exercise_ids = tuple(
                self.order_by().values_list("pk", flat=True).distinct()
            )
            all_covered = True
            for exercise_pk in exercise_ids:
                if not existing_locks.covers(
                    exercise_pk,
                    using,
                    self.model.objects.using(using)
                    .filter(pk=exercise_pk)
                    .values_list("day_id", flat=True)
                    .first(),
                ):
                    all_covered = False
                    break

            if all_covered:
                with transaction.atomic(using=using):
                    result = super().delete()
                    existing_locks.aggregate_locks.recompute_days(
                        set(existing_locks.aggregate_locks.days_by_pk),
                        using=using,
                    )
                    return result

        with transaction.atomic(using=using):
            locks = lock_exercise_deletion_rows(self, using)
            try:
                with activate_exercise_deletion_locks(locks):
                    result = super().delete()
                if locks.aggregate_locks is not None:
                    locks.recompute_days(
                        set(locks.aggregate_locks.days_by_pk),
                        using=using,
                    )
                return result
            finally:
                locks.clear_markers()


class ExerciseManager(
    models.Manager.from_queryset(ExerciseQuerySet)  # type: ignore[misc]
):
    """Manager exposing deletion-safe exercise queryset operations."""


class Exercise(BaseModel):
    """Exercise model class."""

    day = models.ForeignKey(
        "plans.Day",
        on_delete=models.CASCADE,
        related_name="exercises",
    )

    time = models.TimeField(
        default=datetime.time(0, 0),
    )

    EXERCISE_WALK = "walk"
    EXERCISE_RUN = "run"
    EXERCISE_CYCLE = "cycle"
    EXERCISE_GYM = "gym"
    EXERCISE_CHOICES = (
        (EXERCISE_WALK, EXERCISE_WALK.title()),
        (EXERCISE_RUN, EXERCISE_RUN.title()),
        (EXERCISE_CYCLE, EXERCISE_CYCLE.title()),
        (EXERCISE_GYM, EXERCISE_GYM.title()),
    )

    type = models.CharField(
        max_length=20,
        choices=EXERCISE_CHOICES,
    )

    kcals = models.PositiveIntegerField()

    duration = models.DurationField(
        blank=True,
        null=True,
        help_text="hh:mm:ss",
    )

    distance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Distance (km)",
        blank=True,
        null=True,
    )

    objects = ExerciseManager()

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"{self.day} - {self.type.title()} - {self.kcals}kcals"

    _caller_day = None
    _exercise_locks = None
    _exercise_day_ids: tuple[int, ...] = ()
    _previous_day_id = None

    def _lock_write_rows(self, using: str) -> "Exercise | None":
        """Lock deterministic plan/day owners before a write.

        Args:
            using: database alias used by this write.

        Returns:
            Exercise | None: locked persisted exercise for updates.

        Raises:
            _ExerciseOwnerChanged: if owner changed while locking.
        """
        from apps.plans.locks import lock_plan_aggregate_rows

        was_adding = self._state.adding
        previous_day_id = None
        if self.pk is not None:
            previous_day_id = (
                type(self)
                .objects.using(using)
                .filter(pk=self.pk)
                .values_list("day_id", flat=True)
                .first()
            )

        day_ids = {self.day_id}
        if previous_day_id is not None:
            day_ids.add(previous_day_id)

        self._exercise_locks = lock_plan_aggregate_rows(
            using=using,
            day_ids=tuple(sorted(day_ids)),
        )
        locked_days = self._exercise_locks.days_by_pk

        if self._caller_day is None:
            self._caller_day = self._state.fields_cache.get("day")
        if self.day_id is not None:
            self.day = locked_days[self.day_id]
            self._exercise_day_ids = tuple(sorted(day_ids))
        if previous_day_id is None:
            if not was_adding:
                raise type(self).DoesNotExist(
                    "Exercise was deleted before this write acquired its locks"
                )
            return None

        previous = (
            type(self)
            .objects.select_for_update(of=("self",))
            .using(using)
            .get(pk=self.pk)
        )
        if previous.day_id not in day_ids:
            raise _ExerciseOwnerChanged
        return previous

    def _clear_write_locks(self) -> None:
        """Drop transaction scoped lock metadata for this save/delete cycle."""
        if self._exercise_locks is not None:
            self._exercise_locks.clear_markers()
        self._exercise_locks = None
        self._exercise_day_ids = ()
        self._previous_day_id = None

    def _recompute_touched_days(
        self, using: str, previous_day_id: int | None
    ) -> None:
        """Recompute every potentially touched day for this write."""
        if self._exercise_locks is None:
            return

        touched_day_ids = {self.day_id}
        if previous_day_id is not None:
            touched_day_ids.add(previous_day_id)

        for day_id in sorted(day_id for day_id in touched_day_ids if day_id):
            day = self._exercise_locks.days_by_pk[day_id]
            day.save(using=using)

    def save(self, *args, **kwargs) -> None:
        """Atomically save the exercise with canonical aggregate locks."""
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        entered_in_atomic = transaction.get_connection(using).in_atomic_block
        for attempt in range(2):
            try:
                with transaction.atomic(using=using):
                    previous = self._lock_write_rows(using)
                    self._previous_day_id = (
                        previous.day_id if previous is not None else None
                    )
                    super().save(*args, **kwargs)
                    self._recompute_touched_days(using, self._previous_day_id)
                break
            except _ExerciseOwnerChanged as error:
                if entered_in_atomic or attempt == 1:
                    raise RuntimeError(
                        "Exercise owner changed while acquiring "
                        "locks; retry the "
                        "outer transaction"
                    ) from error
            finally:
                self._clear_write_locks()
        else:
            raise RuntimeError("exercise lock retry exhausted")

        if self._caller_day is not None:
            for field in self.day._meta.concrete_fields:
                setattr(
                    self._caller_day,
                    field.attname,
                    getattr(self.day, field.attname),
                )
        self._caller_day = None

    def delete(self, *args, **kwargs):
        """Atomically delete and recompute affected days."""
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        model = cast(type["Exercise"], type(self))
        manager = cast(Any, model).objects
        targets = manager.using(using).filter(pk=self.pk)
        if not targets.exists():
            return models.Model.delete(self, *args, **kwargs)

        existing_locks = get_exercise_deletion_locks()
        if existing_locks is not None and existing_locks.covers(
            self.pk,
            using,
            self.day_id,
        ):
            with transaction.atomic(using=using):
                return targets.delete()

        with transaction.atomic(using=using):
            try:
                locks = lock_exercise_deletion_rows(targets, using)
                with activate_exercise_deletion_locks(locks):
                    return targets.delete()
            finally:
                if locks.aggregate_locks is not None:
                    locks.aggregate_locks.clear_markers()

    @property
    def day_time(self) -> datetime.datetime:
        """Get day and time.

        Returns:
            datetime: day and time.
        """
        return datetime.datetime.combine(self.day.day, self.time).astimezone()


class DaySteps(BaseModel):
    """DaySteps model class."""

    class Meta:
        verbose_name_plural = "Day steps"

    day = models.OneToOneField(
        "plans.Day",
        on_delete=models.CASCADE,
        related_name="steps",
    )

    steps = models.PositiveIntegerField()

    @property
    def kcals(self) -> Decimal:
        """Get kcals.

        Returns:
            Decimal: kcals.
        """
        if not self.steps:
            return Decimal("0")

        return self.steps * Decimal("0.03")
