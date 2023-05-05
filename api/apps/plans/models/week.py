"""Weekly model module."""


import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models

from apps.libs.basemodel import BaseModel

PLAN_LENGTH_DAYS = 7
EXERCISE_RATE = Decimal(1.375)


class WeekPlan(BaseModel):
    """WeekPlan model class."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="calorie_plans",
    )

    measurement = models.ForeignKey(
        "measurements.Measurement",
        on_delete=models.CASCADE,
        related_name="calorie_plans",
    )

    # Parameters
    start_date = models.DateField()

    protein_kg = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        help_text="Protein / kg (gr)",
    )

    fat_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
    )

    # Daily intake
    protein_g_goal_day = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        editable=False,
    )

    fat_g_goal_day = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        editable=False,
    )

    carbs_g_goal_day = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        editable=False,
    )

    # Weekly intake
    protein_g_goal_week = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        editable=False,
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"Week {self.start_date.isocalendar().week}"

    def save(self, *args: list, **kwargs: dict[Any, Any]) -> None:
        """Save instance.

        Args:
            args (list): arguments.
            kwargs (dic[Any, Any]): keywork arguments.
        """
        self.protein_g_goal_day = self.measurement.weight * self.protein_kg
        protein_goal_kcals_day = (
            self.protein_g_goal_day * settings.PROTEIN_KCAL_GRAM
        )
        self.protein_g_goal_week = self.protein_g_goal_day * PLAN_LENGTH_DAYS

        fat_goal_kcals_day = self.tdee_target * self.fat_perc / 100
        self.fat_g_goal_day = fat_goal_kcals_day / settings.FAT_KCAL_GRAM

        carbs_goal_kcals_day = (
            self.tdee_target - protein_goal_kcals_day - fat_goal_kcals_day
        )
        self.carbs_g_goal_day = carbs_goal_kcals_day / settings.CARB_KCAL_GRAM

        super().save(*args, **kwargs)

    def remaining_days(self, today: datetime.date | None = None) -> int:
        """Get remaining days.

        Args:
            today (date): day to consider the current day.

        Returns:
            int: remaining days.
        """
        if not self.start_date:
            return 0

        if not today:
            today = datetime.date.today()

        days_till_end = PLAN_LENGTH_DAYS - (today - self.start_date).days
        if days_till_end > PLAN_LENGTH_DAYS:
            return PLAN_LENGTH_DAYS

        return days_till_end

    # Calories
    @property
    def tdee_target(self) -> Decimal:
        """Get TDEE target.

        Returns:
            Decimal: TDEE target.
        """
        return self.measurement.bmr * EXERCISE_RATE

    @property
    def twee_target(self) -> Decimal:
        """Get TWEE target.

        Returns:
            Decimal: TWEE target.
        """
        return self.tdee_target * PLAN_LENGTH_DAYS

    @property
    def calorie_intake(self) -> Decimal:
        """Get calorie intake.

        Returns:
            Decimal: calorie intake.
        """
        kcals = Decimal(0)
        for day in self.days.all():
            if day.day < datetime.date.today():
                kcals += day.calorie_intake
        return kcals

    @property
    def calorie_expenditure(self) -> Decimal:
        """Get calorie expenditure.

        Returns:
            Decimal: calorie expenditure.
        """
        kcals = Decimal(0)
        for day in self.days.all():
            if day.day < datetime.date.today():
                kcals += day.tdee
        return kcals

    @property
    def calorie_intake_perc(self) -> Decimal:
        """Get calorie intake percentage.

        Returns:
            Decimal: calorie intake percentage.
        """
        return self.calorie_intake * 100 / self.twee_target

    @property
    def calorie_deficit(self) -> Decimal:
        """Get calorie deficit.

        Returns:
            Decimal: calorie deficit.
        """
        return self.calorie_expenditure - self.calorie_intake

    def remaining_kcals(self, today: datetime.date | None = None) -> Decimal:
        """Get remaining kcals.

        Days that surpass the target intake is taken into account to reduce
        the remaining calories. However, for days where the intake is less than
        the target, the calorie intake is considered as the target. This way
        the deficit would be bigger.

        Args:
            today (date): day to consider as current day.

        Returns:
            Decimal: remaining kcals.
        """
        if not today:
            today = datetime.date.today()

        kcals = Decimal(0)

        # Check days
        for day in self.days.all():
            if day.day < today and day.calorie_intake > self.tdee_target:
                kcals -= day.calorie_intake - self.tdee_target

        # Add remaining days
        kcals += self.tdee_target * self.remaining_days(today)

        return kcals

    # Protein
    @property
    def protein_intake_g(self) -> Decimal:
        """Get protein intake in grams.

        Returns:
            Decimal: protein intake in grams.
        """
        grams = Decimal(0)
        for day in self.days.all():
            if day.day < datetime.date.today():
                grams += day.protein_intake_g
        return grams

    @property
    def protein_intake_perc(self) -> Decimal:
        """Get protein intake percentage.

        Returns:
            Decimal: protein intake percentage.
        """
        return self.protein_intake_g * 100 / self.protein_g_goal_week

    @property
    def remaining_protein_g(self) -> Decimal:
        """Get remaining protein in grams.

        Returns:
            Decimal: remaining protein in grams.
        """
        return self.protein_g_goal_week - self.protein_intake_g

    @property
    def remaining_protein_g_day(self) -> Decimal:
        """Get remaining protein in grams per day.

        Returns:
            Decimal: remaining protein in grams per day.
        """
        return self.remaining_protein_g / self.remaining_days()
