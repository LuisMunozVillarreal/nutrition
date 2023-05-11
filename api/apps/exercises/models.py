"""Exercise model module."""


import datetime
from decimal import Decimal

from django.db import models

from apps.libs.basemodel import BaseModel


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

    @property
    def day_time(self) -> datetime.datetime:
        """Get day and time.

        Returns:
            datetime: day and time.
        """
        return datetime.datetime.combine(self.day.day, self.time).astimezone()


class DaySteps(BaseModel):
    """DaySteps model class."""

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
