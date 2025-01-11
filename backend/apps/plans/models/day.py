"""Day model module."""

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models

from apps.foods.models.nutrients import Nutrients

from .intake import Intake


class Day(Nutrients):
    """Day model class."""

    # pylint: disable=too-many-instance-attributes

    # TODO: rename calorie fields by energy  # pylint: disable=fixme
    # Also consider renaming 'energy' to 'energy_kcal', the same way
    # that there is 'protein_g'

    class Meta:
        ordering = ["-plan", "day"]

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
            "account for the calorie intake and goal, respectively. "
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
    calorie_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )

    protein_g_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )

    fat_g_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )

    carbs_g_goal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
    )

    # Intake percentages
    calorie_intake_perc = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        verbose_name="Calorie Intake %",
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
        # For some reason pylint_django it's failing.
        # I believe it's due to protobuf being downgraded due to google-genai
        # pylint: disable=no-member,fixme
        # TODO: Remove this ones protobuf is back to 5.x.x
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
        self.calorie_goal = self._calorie_goal
        self.protein_g_goal = (
            self.plan.protein_g_kg * self.plan.measurement.weight
        )
        self.fat_g_goal = self._fat_g_goal
        self.carbs_g_goal = self._carbs_g_goal

        # Intake percentages
        self.calorie_intake_perc = self._calorie_intake_perc
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
    def _calorie_goal(self) -> Decimal:
        """Get calorie goal.

        Note that if tracked is False, the estimated TDEE would be taken into
        account.

        Day 2 onwards of the plan will take into account any incurred surpluses
        from previous days.

        Returns:
            Decimal: estimated calorie goal.
        """
        return (
            self.tdee
            - Decimal(self.deficit)
            - self.plan.extra_surplus(self.day_num)
        )

    @property
    def _fat_kcal_goal(self) -> Decimal:
        return self._calorie_goal * self.plan.fat_perc / 100

    @property
    def _fat_g_goal(self) -> Decimal:
        return self._fat_kcal_goal / settings.FAT_KCAL_GRAM

    @property
    def _carbs_kcal_goal(self) -> Decimal:
        return self._calorie_goal - self._fat_kcal_goal

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
        good rule of thumb is to consider it the 10% of the BMR.

        Returns:
            Decimal: Thermic Effect of Food.
        """
        return self.plan.measurement.bmr * Decimal("0.1")

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
    def _calorie_intake_perc(self) -> Decimal:
        """Get calorie intake percentage.

        Returns:
             Decimal: calorie intake percentage.
        """
        if not self.calorie_goal:
            return Decimal("0")

        return self.energy * 100 / self.calorie_goal

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
    def calorie_deficit(self) -> Decimal:
        """Get calorie deficit.

        Returns:
             Decimal: calorie deficit.
        """
        if not self.calorie_goal:
            return Decimal("0")

        deficit = self.calorie_goal - self.energy
        if deficit > 0:
            return deficit

        return Decimal("0")

    @property
    def calorie_surplus(self) -> Decimal:
        """Get calorie surplus.

        Returns:
             Decimal: calorie surplus.
        """
        if not self.calorie_goal:
            return Decimal("0")

        surplus = self.energy - self.calorie_goal
        if surplus > 0:
            return surplus

        return Decimal("0")
