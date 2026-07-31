"""Intake models module."""

from typing import Any

from django.db import models, router, transaction

from apps.foods.models.nutrients import NUTRIENT_LIST, Nutrients


class Intake(Nutrients):
    """Intake models class."""

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
        from apps.plans.locks import lock_plan_aggregate_rows

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
