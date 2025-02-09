"""Intake models module."""

from typing import Any

from django.db import models

from apps.foods.models.nutrients import NUTRIENT_LIST, Nutrients


class Intake(Nutrients):
    """Intake models class."""

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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        self.meal_order = self.MEAL_ORDER[self.meal]
        self.processed = self.food is not None

        for nutrient in NUTRIENT_LIST:
            value = 0
            if self.food:
                value = getattr(self.food, nutrient) or 0
            setattr(self, nutrient, value * self.num_servings)

        super().save(*args, **kwargs)


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
