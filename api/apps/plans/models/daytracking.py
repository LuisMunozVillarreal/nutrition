"""DayTracking model module."""


import datetime
from decimal import Decimal

from django.db import models

from apps.foods.models.nutrients import Nutrients


class DayTracking(Nutrients):
    """DayTracking model class."""

    class Meta:
        ordering = ["plan", "-day"]

    plan = models.ForeignKey(
        "plans.WeekPlan",
        on_delete=models.CASCADE,
        related_name="days",
    )

    day = models.DateField()

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return f"{str(self.plan)} - {self.day.strftime('%A')}"

    @property
    def num_foods(self) -> int:
        """Get number of foods.

        Returns:
            int: number of foods.
        """
        return self.foods.count()

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
        res = self.exercises.aggregate(total_kcals=models.Sum("kcals"))
        return res["total_kcals"] or 0

    @property
    def tdee(self) -> Decimal:
        """Total Daily Energy Expenditure.

        TDEE = BMR + NEAT + TEF + EAT

        BMR = Basal Metabolic Rate
        NEAT = Non-Exercise Activity Thermogenesis
        TEF = Thermic Efect of Food
        EAT = Exercise Activity Thermogenesis

        Returns:
            Decimal: tdee.
        """
        return (
            self.plan.measurement.bmr
            + self.neat
            + self.tef
            + self.eat
            - self.plan.deficit
        )

    @property
    def estimated_calorie_goal(self) -> Decimal:
        """Get estimated calorie goal.

        Returns:
            Decimal: estimated calorie goal.
        """
        if not self.day:
            return Decimal("0")

        now = datetime.datetime.combine(
            self.day, datetime.time(0, 0)
        ).astimezone()
        today = now.date()

        return self.plan.remaining_kcals(now) / self.plan.remaining_days(today)

    @property
    def calorie_intake(self) -> Decimal:
        """Get calorie intake.

        Returns:
             Decimal: calorie intake.
        """
        kcals = Decimal("0")
        for food in self.foods.all():
            kcals += food.calories
        return kcals

    @property
    def calorie_intake_perc(self) -> Decimal:
        """Get calorie intake percentage.

        Returns:
             Decimal: calorie intake percentage.
        """
        return round(self.calorie_intake * 100 / self.tdee, 2)

    @property
    def calorie_deficit(self) -> Decimal:
        """Get calorie deficit.

        Returns:
             Decimal: calorie deficit.
        """
        deficit = self.tdee - self.calorie_intake
        if deficit > 0:
            return deficit

        return Decimal("0")

    @property
    def calorie_surplus(self) -> Decimal:
        """Get calorie surplus.

        Returns:
             Decimal: calorie surplus.
        """
        surplus = self.calorie_intake - self.tdee
        if surplus > 0:
            return surplus

        return Decimal("0")

    @property
    def protein_intake_g(self) -> Decimal:
        """Get protein intake in grams.

        Returns:
            Decimal: protein intake in grams.
        """
        grams = Decimal("0")
        for food in self.foods.all():
            grams += food.protein_g
        return grams
