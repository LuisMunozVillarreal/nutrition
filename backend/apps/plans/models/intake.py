"""Intake models module."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, cast

from django.apps import apps
from django.db import models, router, transaction

from apps.foods.models.nutrients import NUTRIENT_LIST, Nutrients
from apps.plans.locks import PlanAggregateLocks, lock_plan_aggregate_rows


@dataclass
class IntakeDeletionLocks:
    """Rows locked before Django collects a bulk intake deletion."""

    using: str
    aggregate_locks: PlanAggregateLocks
    intakes: tuple[models.Model, ...]

    def covers(self, intake_id: int, day_id: int, using: str) -> bool:
        """Return whether this bundle owns the intake and its day locks.

        Args:
            intake_id (int): Intake primary key that must be covered.
            day_id (int): Parent day primary key that must be covered.
            using (str): Database alias on which locks must be held.

        Returns:
            bool: Whether this bundle covers the requested hierarchy.
        """
        return (
            self.using == using
            and any(intake.pk == intake_id for intake in self.intakes)
            and self.aggregate_locks.covers_days((day_id,), using)
        )


_active_intake_deletion_locks: ContextVar[IntakeDeletionLocks | None] = (
    ContextVar("active_intake_deletion_locks", default=None)
)


def get_intake_deletion_locks() -> IntakeDeletionLocks | None:
    """Return the deletion lock bundle active in the current execution context.

    Returns:
        IntakeDeletionLocks | None: Active lock bundle, if any.
    """
    return _active_intake_deletion_locks.get()


@contextmanager
def activate_intake_deletion_locks(
    locks: IntakeDeletionLocks,
) -> Iterator[None]:
    """Expose pre-collector locks to intake deletion signal handlers.

    Args:
        locks (IntakeDeletionLocks): Bundle held by the outer transaction.
    """
    token = _active_intake_deletion_locks.set(locks)
    try:
        yield
    finally:
        _active_intake_deletion_locks.reset(token)


def lock_intake_deletion_rows(
    targets: models.QuerySet, using: str
) -> IntakeDeletionLocks:
    """Lock all target plans, days, and intakes in canonical PK order.

    Args:
        targets (models.QuerySet): Complete affected intake selection.
        using (str): Database alias used by the deletion.

    Returns:
        IntakeDeletionLocks: Locked hierarchy exposed to collector signals.
    """
    target_rows = list(targets.order_by().values_list("pk", "day_id"))
    intake_ids = tuple(sorted(row[0] for row in target_rows))
    day_ids = tuple(sorted({row[1] for row in target_rows}))
    aggregate_locks = lock_plan_aggregate_rows(using=using, day_ids=day_ids)
    intakes = tuple(
        intake
        for intake in targets.model.objects.select_for_update(of=("self",))
        .using(using)
        .filter(pk__in=intake_ids)
        .order_by("pk")
    )
    return IntakeDeletionLocks(using, aggregate_locks, intakes)


class IntakeQuerySet(models.QuerySet):
    """QuerySet that locks the complete intake hierarchy before collection."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Delete selected intakes under canonical pre-collector locks.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        using = self.db
        with transaction.atomic(using=using):
            locks = lock_intake_deletion_rows(self, using)
            try:
                with activate_intake_deletion_locks(locks):
                    return super().delete()
            finally:
                locks.aggregate_locks.clear_markers()


class IntakeManager(
    models.Manager.from_queryset(IntakeQuerySet)  # type: ignore[misc]
):
    """Manager exposing deletion-safe intake querysets."""


def intake_targets_for_cascade(
    targets: models.QuerySet, using: str
) -> models.QuerySet:
    """Return intakes cascaded by a Day or WeekPlan deletion target.

    Args:
        targets (models.QuerySet): Day or WeekPlan roots being deleted.
        using (str): Database alias used by the deletion.

    Returns:
        models.QuerySet: Complete cascaded intake selection.
    """
    intake_model = apps.get_model("plans", "Intake")
    if targets.model._meta.label_lower == "plans.day":
        return intake_model.objects.using(using).filter(
            day_id__in=targets.order_by().values("pk")
        )
    if targets.model._meta.label_lower == "plans.weekplan":
        return intake_model.objects.using(using).filter(
            day__plan_id__in=targets.order_by().values("pk")
        )
    return intake_model.objects.using(using).none()


class IntakeCascadeQuerySet(models.QuerySet):
    """QuerySet that prelocks intakes reached through plan/day cascades."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Delete roots after locking every cascaded intake hierarchy.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        using = self.db
        intake_targets = intake_targets_for_cascade(self, using)
        if not intake_targets.exists():
            return super().delete()
        with transaction.atomic(using=using):
            locks = lock_intake_deletion_rows(intake_targets, using)
            try:
                with activate_intake_deletion_locks(locks):
                    return super().delete()
            finally:
                locks.aggregate_locks.clear_markers()


class IntakeCascadeManager(
    models.Manager.from_queryset(IntakeCascadeQuerySet)  # type: ignore[misc]
):
    """Manager exposing intake-safe plan/day cascade deletion."""


class IntakeCascadeDeletionMixin:
    """Prelock cascaded intakes for direct plan/day instance deletion."""

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Delete this root under the same locks as its custom queryset.

        Args:
            args (Any): Positional arguments forwarded to Django deletion.
            kwargs (Any): Keyword arguments forwarded to Django deletion.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        instance = cast(models.Model, self)
        model = type(instance)
        using = kwargs.get("using") or router.db_for_write(
            model, instance=instance
        )
        manager = cast(Any, model).objects
        targets = manager.using(using).filter(pk=instance.pk)
        intake_targets = intake_targets_for_cascade(targets, using)
        if not intake_targets.exists():
            return models.Model.delete(instance, *args, **kwargs)
        with transaction.atomic(using=using):
            locks = lock_intake_deletion_rows(intake_targets, using)
            try:
                with activate_intake_deletion_locks(locks):
                    return models.Model.delete(instance, *args, **kwargs)
            finally:
                locks.aggregate_locks.clear_markers()


class Intake(Nutrients):
    """Intake models class."""

    objects = IntakeManager()

    _caller_day: models.Model | None = None
    _nutrition_day_ids: tuple[int, ...] = ()
    _nutrition_locks: Any = None

    day = models.ForeignKey(
        "plans.Day",
        on_delete=models.CASCADE,
        related_name="intakes",
    )

    food = models.ForeignKey(
        "foods.Serving",
        on_delete=models.CASCADE,
        default=None,
        null=True,
        blank=True,
        related_name="intakes",
    )

    num_servings = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=1,
    )

    MEAL_BREAKFAST = "breakfast"
    MEAL_LUNCH = "lunch"
    MEAL_SNACK = "snack"
    MEAL_DINNER = "dinner"
    MEAL_CHOICES = (
        (MEAL_BREAKFAST, MEAL_BREAKFAST.title()),
        (MEAL_LUNCH, MEAL_LUNCH.title()),
        (MEAL_SNACK, MEAL_SNACK.title()),
        (MEAL_DINNER, MEAL_DINNER.title()),
    )

    meal = models.CharField(
        max_length=20,
        choices=MEAL_CHOICES,
    )

    MEAL_ORDER = {
        MEAL_BREAKFAST: 0,
        MEAL_LUNCH: 1,
        MEAL_SNACK: 2,
        MEAL_DINNER: 3,
    }

    meal_order = models.PositiveIntegerField(
        editable=False,
    )

    notes = models.TextField(
        blank=True,
    )

    processed = models.BooleanField(
        default=True,
        editable=False,
        help_text="Indicates whether the intake's notes have been processed.",
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        if self.food:
            return (
                f"{str(self.day)} - {str(self.food)} - {self.meal.title()} -"
                f" {self.food.serving_size} ({self.food.serving_unit})"
            )

        return f"{str(self.day)} - {self.meal.title()} (No processed)"

    def _lock_write_rows(self, using: str) -> "Intake | None":
        """Lock aggregate owners before an existing intake, in that order.

        Every intake write uses the global lock order ``WeekPlan`` then ``Day``
        (ascending primary key within each model), then ``Intake``. The day lock
        serializes creates, for which no intake row exists yet, and remains held
        while signals update cupboard state and recompute day/plan state.

        Args:
            using (str): database alias used by the write.

        Returns:
            Intake | None: locked persisted intake for an update, if any.
        """
        intake_model = type(self)
        was_adding = self._state.adding
        previous_day_id = None
        if self.pk is not None:
            previous_day_id = (
                intake_model.objects.using(using)
                .filter(pk=self.pk)
                .values_list("day_id", flat=True)
                .first()
            )

        day_ids = {self.day_id}
        if previous_day_id is not None:
            day_ids.add(previous_day_id)

        aggregate_locks = lock_plan_aggregate_rows(
            using=using, day_ids=day_ids
        )
        locked_days = aggregate_locks.days_by_pk
        self._caller_day = self._state.fields_cache.get("day")
        self.day = locked_days[self.day_id]
        self._nutrition_day_ids = tuple(sorted(day_ids))
        self._nutrition_locks = aggregate_locks

        if previous_day_id is None:
            if not was_adding:
                raise intake_model.DoesNotExist(
                    "Intake was deleted before this write acquired its locks"
                )
            return None
        return (
            intake_model.objects.select_for_update()
            .using(using)
            .get(pk=self.pk)
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Atomically save an intake and all of its derived effects.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        with transaction.atomic(using=using):
            try:
                previous = self._lock_write_rows(using)
                self.meal_order = self.MEAL_ORDER[self.meal]

                if previous is not None and self.food is None:
                    removed_food_without_macro_edits = (
                        previous.food_id is not None
                        and all(
                            (getattr(self, nutrient) or 0)
                            == (getattr(previous, nutrient) or 0)
                            for nutrient in NUTRIENT_LIST
                        )
                    )
                    if removed_food_without_macro_edits:
                        for nutrient in NUTRIENT_LIST:
                            setattr(self, nutrient, 0)

                self.processed = self.food is not None or any(
                    (getattr(self, nutrient) or 0) != 0
                    for nutrient in NUTRIENT_LIST
                )

                if self.food:
                    for nutrient in NUTRIENT_LIST:
                        value = getattr(self.food, nutrient) or 0
                        setattr(self, nutrient, value * self.num_servings)

                super().save(*args, **kwargs)
            finally:
                if self._nutrition_locks is not None:
                    self._nutrition_locks.clear_markers()
                self._nutrition_locks = None

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Delete an intake and its aggregate/cupboard effects atomically.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.

        Returns:
            tuple[int, dict[str, int]]: Django deletion result.
        """
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        with transaction.atomic(using=using):
            try:
                self._lock_write_rows(using)
                return super().delete(*args, **kwargs)
            finally:
                if self._nutrition_locks is not None:
                    self._nutrition_locks.clear_markers()
                self._nutrition_locks = None


class IntakePicture(models.Model):
    """IntakePicture models class."""

    intake = models.ForeignKey(
        Intake,
        on_delete=models.CASCADE,
        related_name="pictures",
    )

    description = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    picture = models.ImageField(
        upload_to="intake_pictures",
    )
