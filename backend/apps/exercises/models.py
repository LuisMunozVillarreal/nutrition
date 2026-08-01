"""Exercise model module."""

import datetime
from decimal import Decimal

from django.db import models, router, transaction

from apps.libs.basemodel import BaseModel


class _ExerciseOwnerChanged(RuntimeError):
    """Signal that exercise owner day changed while acquiring locks."""


_ExerciseLocks = tuple[str, int] | tuple[()]


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
        with transaction.atomic(using=using):
            try:
                self._lock_write_rows(using)
                self._previous_day_id = self.day_id
                return super().delete(*args, **kwargs)
            finally:
                self._recompute_touched_days(using, self._previous_day_id)
                self._clear_write_locks()

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
