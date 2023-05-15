"""Week model module."""


import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models

from apps.libs.basemodel import BaseModel

PLAN_LENGTH_DAYS = 7
EXERCISE_RATE = Decimal("1.375")


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

    deficit = models.PositiveIntegerField(
        default=0,
        verbose_name="Deficit (kcals/day)",
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

    def save(self, *args: Any, **kwargs: Any) -> None:
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

        fat_goal_kcals_day = self.estimated_tdee * self.fat_perc / 100
        self.fat_g_goal_day = fat_goal_kcals_day / settings.FAT_KCAL_GRAM

        carbs_goal_kcals_day = (
            self.estimated_tdee - protein_goal_kcals_day - fat_goal_kcals_day
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

        if days_till_end < 0:
            return 0

        return days_till_end

    # Calories
    @property
    def estimated_tdee(self) -> Decimal:
        """Get estimated TDEE.

        Returns:
            Decimal: estimated TDEE.
        """
        return (
            self.measurement.bmr * EXERCISE_RATE - self.deficit
        ).normalize()

    @property
    def estimated_twee(self) -> Decimal:
        """Get estimated TWEE.

        Returns:
            Decimal: estimated TWEE.
        """
        return self.estimated_tdee * PLAN_LENGTH_DAYS

    @property
    def calorie_intake(self) -> Decimal:
        """Get calorie intake.

        Returns:
            Decimal: calorie intake.
        """
        kcals = Decimal("0")
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
        kcals = Decimal("0")
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
        return round(self.calorie_intake * 10000 / self.estimated_twee, 2)

    @property
    def calorie_deficit(self) -> Decimal:
        """Get calorie deficit.

        Returns:
            Decimal: calorie deficit.
        """
        return self.calorie_expenditure - self.calorie_intake

    def remaining_kcals(self, now: datetime.datetime | None = None) -> Decimal:
        """Get remaining kcals.

        Days that surpass the TDEE intake for that day is taken into account
        to reduce the remaining calories. However, for days where the intake
        is less than the TDEE for that day, the calorie intake is considered
        as the TDEE for that day. This way the deficit will be bigger.

        Today's foods already consumed are also taken into account.

        Args:
            now (datetime): time to be considered as the current one.

        Returns:
            Decimal: remaining kcals.
        """
        if not now:
            now = datetime.datetime.now().astimezone()

        kcals = Decimal("0")

        # Check days
        for day in self.days.all():
            if day.day < now.date() and day.calorie_surplus:
                kcals -= day.calorie_surplus
            elif day.day == now.date():
                for food in day.intake.all():
                    if food.day_time <= now:
                        kcals -= food.calories

        # Add remaining days
        kcals += self.estimated_tdee * self.remaining_days(now.date())

        return kcals

    # Protein
    @property
    def protein_intake_g(self) -> Decimal:
        """Get protein intake in grams.

        Returns:
            Decimal: protein intake in grams.
        """
        grams = Decimal("0")
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
        return round(
            self.protein_intake_g * 10000 / self.protein_g_goal_week, 2
        )

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
        remaining_days = self.remaining_days()
        if not remaining_days:
            return Decimal("0")

        return self.remaining_protein_g / remaining_days
