"""Day model module."""

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib import admin
from django.db import models

from apps.foods.models.nutrients import Nutrients
from apps.libs.admin import progress_bar
from apps.libs.utils import round_no_trailing_zeros

from .intake import Intake


class Day(Nutrients):
    """Day model class."""

    # pylint: disable=too-many-instance-attributes

    class Meta:
        ordering = ["-plan", "-day"]

    plan = models.ForeignKey(
        "plans.WeekPlan",
        on_delete=models.CASCADE,
        related_name="days",
    )

    day = models.DateField()

    # Parameters
    day_num = models.PositiveIntegerField(
        help_text="Day in the plan.",
    )

    deficit = models.PositiveIntegerField(
        default=0,
        verbose_name="Planned deficit (kcals)",
    )

    # Flags
    tracked = models.BooleanField(
        default=True,
        help_text=(
            "Indicates whether the day's intakes and exercises are taken into "
            "account for the energy intake and goal, respectively. "
            "Otherwise, the estimated values are used. This field is "
            "toggled to true as soon as an exercise or an intake is logged."
        ),
    )

    completed = models.BooleanField(
        default=False,
        editable=False,
        help_text=(
            "Indicates whether the day has been completed and "
            "has all the required information inputted."
        ),
    )

    breakfast_flag = models.BooleanField(
        default=False,
        help_text=(
            "Indicates whether breakfast was logged. "
            "Unprocessed breakfast won't count as logged."
        ),
        verbose_name="Breakfast",
    )
    breakfast_exc = models.BooleanField(
        default=False,
        help_text="Indicates whether breakfast is exceptionally not logged.",
    )

    lunch_flag = models.BooleanField(
        default=False,
        help_text=(
            "Indicates whether lunch was logged. "
            "Unprocessed lunch won't count as logged."
        ),
        verbose_name="Lunch",
    )
    lunch_exc = models.BooleanField(
        default=False,
        help_text="Indicates whether lunch is exceptionally not logged.",
    )

    snack_flag = models.BooleanField(
        default=False,
        help_text=(
            "Indicates whether snacks were logged. "
            "Unprocessed snacks won't count as logged."
        ),
        verbose_name="Snacks",
    )
    snack_exc = models.BooleanField(
        default=False,
        help_text="Indicates whether snacks are exceptionally not logged.",
    )

    dinner_flag = models.BooleanField(
        default=False,
        help_text=(
            "Indicates whether dinner was logged. "
            "Unprocessed dinner won't count as logged."
        ),
        verbose_name="Dinner",
    )
    dinner_exc = models.BooleanField(
        default=False,
        help_text="Indicates whether dinner is exceptionally not logged.",
    )

    exercises_flag = models.BooleanField(
        default=False,
        help_text="Indicates whether exercise was logged.",
        verbose_name="Exercises",
    )
    exercises_exc = models.BooleanField(
        default=False,
        help_text="Indicates whether exercises are exceptionally not logged.",
    )

    steps_flag = models.BooleanField(
        default=False,
        help_text="Indicates whether steps were logged.",
        verbose_name="Steps",
    )
    steps_exc = models.BooleanField(
        default=False,
        help_text="Indicates whether steps are exceptionally not logged.",
    )

    # Goals
    energy_kcal_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Energy (kcal) Goal",
    )

    protein_g_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Protein (g) Goal",
    )

    fat_g_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Fat (g) Goal",
    )

    carbs_g_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Carbs (g) Goal",
    )

    # Intake percentages
    energy_kcal_intake_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Energy Intake %",
    )

    protein_g_intake_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Protein Intake %",
    )

    fat_g_intake_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Fat Intake %",
    )

    carbs_g_intake_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Carbs Intake %",
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return f"{str(self.plan)} - {self.day.strftime('%A')}"

    @property
    def weekday(self) -> str:
        """Get weekday.

        Returns:
            str: weekday.
        """
        return self.day.strftime("%A")

    @property
    def num_foods(self) -> int:
        """Get number of foods.

        Returns:
            int: number of foods.
        """
        return self.intakes.count()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save instance.

        Args:
            args (list): arguments.
            kwargs (Any): keywork arguments.
        """
        # Goals
        self.energy_kcal_goal = self._energy_kcal_goal
        self.protein_g_goal = (
            self.plan.protein_g_kg * self.plan.measurement.weight
        )
        self.fat_g_goal = self._fat_g_goal
        self.carbs_g_goal = self._carbs_g_goal

        # Intake percentages
        self.energy_kcal_intake_perc = self._energy_kcal_intake_perc
        self.protein_g_intake_perc = self._protein_g_intake_perc
        self.fat_g_intake_perc = self._fat_g_intake_perc
        self.carbs_g_intake_perc = self._carbs_g_intake_perc

        # Flags
        self.breakfast_flag = (
            self.breakfast_exc
            or bool(self.id)
            and not (
                self.intakes.filter(meal=Intake.MEAL_BREAKFAST)
                .filter(processed=False)
                .exists()
            )
            and self.intakes.filter(meal=Intake.MEAL_BREAKFAST).exists()
        )
        self.lunch_flag = (
            self.lunch_exc
            or bool(self.id)
            and not (
                self.intakes.filter(meal=Intake.MEAL_LUNCH)
                .filter(processed=False)
                .exists()
            )
            and self.intakes.filter(meal=Intake.MEAL_LUNCH).exists()
        )
        self.snack_flag = (
            self.snack_exc
            or bool(self.id)
            and not (
                self.intakes.filter(meal=Intake.MEAL_SNACK)
                .filter(processed=False)
                .exists()
            )
            and self.intakes.filter(meal=Intake.MEAL_SNACK).exists()
        )
        self.dinner_flag = (
            self.dinner_exc
            or bool(self.id)
            and not (
                self.intakes.filter(meal=Intake.MEAL_DINNER)
                .filter(processed=False)
                .exists()
            )
            and self.intakes.filter(meal=Intake.MEAL_DINNER).exists()
        )
        self.exercises_flag = (
            self.exercises_exc or bool(self.id) and self.exercises.exists()
        )
        self.steps_flag = self.steps_exc or hasattr(self, "steps")

        self.completed = (
            self.breakfast_flag
            and self.lunch_flag
            and self.snack_flag
            and self.dinner_flag
            and self.exercises_flag
            and self.steps_flag
        )

        super().save(*args, **kwargs)

    # Goals calculators
    @property
    def _energy_kcal_goal(self) -> Decimal:
        """Get energy goal.

        Note that if tracked is False, the estimated TDEE would be taken into
        account.

        Returns:
            Decimal: estimated energy goal.
        """
        return self.tdee - Decimal(self.deficit)

    @property
    def _fat_kcal_goal(self) -> Decimal:
        return self._energy_kcal_goal * self.plan.fat_perc / 100

    @property
    def _fat_g_goal(self) -> Decimal:
        return self._fat_kcal_goal / settings.FAT_KCAL_GRAM

    @property
    def _carbs_kcal_goal(self) -> Decimal:
        return self._energy_kcal_goal - self._fat_kcal_goal

    @property
    def _carbs_g_goal(self) -> Decimal:
        return self._carbs_kcal_goal / settings.CARB_KCAL_GRAM

    # TDEE
    @property
    def neat(self) -> Decimal:
        """Get Non-Exercise Activity Thermogenesis.

        Returns:
            Decimal: Non-Exercise Activity Thermogenesis.
        """
        if hasattr(self, "steps"):
            return self.steps.kcals

        return Decimal("0")

    @property
    def tef(self) -> Decimal:
        """Get Thermic Effect of Food.

        There is non easy way to calculate this. Literature indicates that a
        good rule of thumb is to consider it the 10% of the energy consumed.

        Returns:
            Decimal: Thermic Effect of Food.
        """
        return self.energy_kcal * Decimal("0.1")

    @property
    def eat(self) -> int:
        """Get Exercise Activity Thermogenesis.

        Returns:
            int: Exercise Activity Thermogenesis.
        """
        if self.id is None:
            return 0

        res = self.exercises.aggregate(total_kcals=models.Sum("kcals"))
        return res["total_kcals"] or 0

    @property
    def tdee(self) -> Decimal:
        """Get Total Daily Energy Expenditure.

        TDEE = BMR + NEAT + TEF + EAT

        BMR = Basal Metabolic Rate
        NEAT = Non-Exercise Activity Thermogenesis
        TEF = Thermic Efect of Food
        EAT = Exercise Activity Thermogenesis

        Note that if tracked is False, an estimation based on the exercise rate
        is returned.

        Returns:
            Decimal: tdee.
        """
        if self.tracked:
            return self.plan.measurement.bmr + self.neat + self.tef + self.eat

        return (
            self.plan.measurement.bmr * self.plan.EXERCISE_RATE
        ).normalize()

    # Intakes percentages calculators
    @property
    def _energy_kcal_intake_perc(self) -> Decimal:
        """Get energy intake percentage.

        Returns:
             Decimal: energy intake percentage.
        """
        if not self.energy_kcal_goal:
            return Decimal("0")

        return self.energy_kcal * 100 / self.energy_kcal_goal

    @property
    def _protein_g_intake_perc(self) -> Decimal:
        """Get protein intake percentage.

        Returns:
             Decimal: protein intake percentage.
        """
        if not self.protein_g_goal:
            return Decimal("0")

        return self.protein_g * 100 / self.protein_g_goal

    @property
    def _fat_g_intake_perc(self) -> Decimal:
        """Get fat intake percentage.

        Returns:
             Decimal: fat intake percentage.
        """
        if not self.fat_g_goal:
            return Decimal("0")

        return self.fat_g * 100 / self.fat_g_goal

    @property
    def _carbs_g_intake_perc(self) -> Decimal:
        """Get carbs intake percentage.

        Returns:
             Decimal: carbs intake percentage.
        """
        if not self.carbs_g_goal:
            return Decimal("0")

        return self.carbs_g * 100 / self.carbs_g_goal

    @property
    @admin.display(description="Energy (kcal) Goal Diff")
    def energy_kcal_goal_diff(self) -> Decimal:
        """Get energy goal diff.

        A positive number diff is achieved deficit.
        A negative number diff is incurred surplus.

        Returns:
             Decimal: energy diff.
        """
        if not self.energy_kcal_goal:
            return Decimal("0")

        return self.energy_kcal_goal - self.energy_kcal

    @property
    @admin.display(description="Energy (kcal) Goal Acc. Diff")
    def energy_kcal_goal_accumulated_diff(self) -> Decimal:
        """Get accumulated energy goal diff.

        Returns:
            Decimal: accumulated energy goal diff.
        """
        return self.plan.energy_kcal_goal_accumulated_diff(self.day_num)

    @admin.display(description="Energy")
    def energy_kcal_intake_progress_bar(self) -> str:
        """Get energy intake progress bar.

        Returns:
            str: progress bar.
        """
        return progress_bar(self, "energy_kcal_intake_perc")

    @admin.display(description="Fat")
    def fat_g_intake_progress_bar(self) -> str:
        """Get fat intake progress bar.

        Returns:
            str: progress bar.
        """
        return progress_bar(self, "fat_g_intake_perc")

    @admin.display(description="Carbs")
    def carbs_g_intake_progress_bar(self) -> str:
        """Get carbs intake progress bar.

        Returns:
            str: progress bar.
        """
        return progress_bar(self, "carbs_g_intake_perc")

    @admin.display(description="Protein")
    def protein_g_intake_progress_bar(self) -> str:
        """Get protein intake progress bar.

        Returns:
            str: progress bar.
        """
        return progress_bar(self, "protein_g_intake_perc")

    @admin.display(description="TDEE")
    def round_tdee(self) -> Decimal:
        """Round TDEE.

        Returns:
            Decimal: rounded TDEE.
        """
        return round_no_trailing_zeros(self.tdee)
