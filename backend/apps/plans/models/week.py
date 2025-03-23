"""Week model module."""

from decimal import Decimal
from typing import Any

from django.db import models

from apps.libs.basemodel import BaseModel


class WeekPlan(BaseModel):
    """WeekPlan model class."""

    PLAN_LENGTH_DAYS = 7
    # The following represent percentages. They should all sum 700
    DEFICIT_DISTRIBUTION = [90, 80, 90, 110, 110, 110, 110]
    EXERCISE_RATE = Decimal("1.375")

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="week_plans",
    )

    measurement = models.ForeignKey(
        "measurements.Measurement",
        on_delete=models.CASCADE,
        related_name="week_plans",
    )

    # Parameters
    start_date = models.DateField(
        help_text=(
            "This field should not be changed after creation. "
            "Dependant fields and objects won't be recalculated."
        ),
    )

    protein_g_kg = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Protein (g/kg)",
        help_text=(
            "Protein grams consumed per kilo of body weight. "
            "The recommended value is 2.3-2.8g/kg for cutting and "
            "1.8-2.2g/kg for bulking."
        ),
    )

    fat_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Fat (%)",
        help_text=(
            "Fat percentage of the total energy goal. "
            "The recommended value is 15-25% for cutting and "
            "20-30% for bulking."
        ),
    )

    deficit = models.PositiveIntegerField(
        default=0,
        verbose_name="Deficit (kcals/day)",
        help_text=(
            "This deficit is the average per day. It might be different on "
            "each day of the week if the distribution is not even."
        ),
    )

    completed = models.BooleanField(
        default=False,
        editable=False,
        help_text=(
            "Indicates whether the week has been completed and "
            "has all the required information inputted."
        ),
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"Week {self.start_date.isocalendar().week}"

    @property
    def twee(self) -> Decimal:
        """Get TWEE.

        Returns:
            Decimal: TWEE.
        """
        twee = Decimal("0")
        for day in self.days.all():
            twee += day.tdee
        return twee

    @property
    def energy_kcal_goal(self) -> Decimal:
        """Get energy goal.

        Returns:
            Decimal: energy goal.
        """
        goal = Decimal("0")
        for day in self.days.all():
            goal += day.energy_kcal_goal
        return goal

    # Intake
    @property
    def energy_kcal(self) -> Decimal:
        """Get energy intake.

        Returns:
            Decimal: energy intake.
        """
        kcals = Decimal("0")
        for day in self.days.all():
            kcals += day.energy_kcal
        return kcals

    @property
    def energy_kcal_intake_perc(self) -> Decimal:
        """Get energy intake percentage.

        Returns:
            Decimal: energy intake percentage.
        """
        if not self.energy_kcal_goal:
            return Decimal("0")

        return self.energy_kcal * 100 / self.energy_kcal_goal

    @property
    def energy_kcal_goal_diff(self) -> Decimal:
        """Get energy goal diff.

        Returns:
            Decimal: energy diff.
        """
        diff = Decimal("0")
        for day in self.days.all():
            diff += day.energy_kcal_goal_diff
        return diff

    def energy_kcal_goal_accumulated_diff(self, day_num: int) -> Decimal:
        """Get accumulated energy goal diff.

        Args:
            day_num (int): day number.

        Returns:
            Decimal: accumulated energy goal diff.
        """
        diff = Decimal("0")
        for day in self.days.filter(day_num__lte=day_num):
            if day.completed:
                diff += day.energy_kcal_goal_diff

            # If the day isn't completed, only adds difference if it's surplus
            elif day.energy_kcal_goal_diff < 0:
                diff += day.energy_kcal_goal_diff

        return diff

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance into the db.

        Args:
            args (list): arguments.
            kwargs (dict): keyword arguments.
        """
        self.completed = (
            bool(self.id) and not self.days.filter(completed=False).exists()
        )

        super().save(*args, **kwargs)
