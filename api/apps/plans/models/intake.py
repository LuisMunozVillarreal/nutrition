"""Intake models module."""


import datetime
from typing import Any

from django.db import models

from apps.foods.models.proportion import FoodProportion


class Intake(FoodProportion):
    """Intake models class."""

    day = models.ForeignKey(
        "plans.Day",
        on_delete=models.CASCADE,
        related_name="intake",
    )

    planned_time = models.TimeField(
        default=datetime.time(0, 0),
    )

    food = models.ForeignKey(
        "foods.Food",
        on_delete=models.CASCADE,
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

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return (
            f"{str(self.day)} - {str(self.food)} - {self.meal.title()} -"
            f" {self.serving_size} ({self.serving_unit})"
        )

    @property
    def day_time(self) -> datetime.datetime:
        """Get day and time.

        Returns:
            datetime: day and time.
        """
        return datetime.datetime.combine(
            self.day.day, self.planned_time
        ).astimezone()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        self.meal_order = self.MEAL_ORDER[self.meal]
        super().save(*args, **kwargs)