"""DayTracking model module."""


import datetime
from decimal import Decimal

from django.db import models

from apps.foods.models.nutrients import Nutrients
from apps.libs.basemodel import BaseModel


class DayTracking(BaseModel, Nutrients):
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
    def neat(self) -> int:
        """Get Non-Exercise Activity Thermogenesis.

        Returns:
            int: Non-Exercise Activity Thermogenesis.
        """
        return 0

    @property
    def tef(self) -> int:
        """Get Thermic Effect of Food.

        Returns:
            int: Thermic Effect of Food.
        """
        return 0

    @property
    def eat(self) -> int:
        """Get Exercise Activity Thermogenesis.

        Returns:
            int: Exercise Activity Thermogenesis.
        """
        return 0

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
        return self.plan.measurement.bmr + self.neat + self.tef + self.eat

    @property
    def calorie_goal(self) -> Decimal:
        """Get calorie goal.

        Returns:
            Decimal: calorie goal.
        """
        if not self.day:
            return Decimal(0)

        today = None
        if self.day < datetime.date.today():
            today = self.day

        return self.plan.remaining_kcals(today) / self.plan.remaining_days(
            today
        )

    @property
    def calorie_intake(self) -> Decimal:
        """Get calorie intake.

        Returns:
             Decimal: calorie intake.
        """
        kcals = Decimal(0)
        for food in self.foods.all():
            kcals += food.calories
        return kcals

    @property
    def calorie_intake_perc(self) -> Decimal:
        """Get calorie intake percentage.

        Returns:
             Decimal: calorie intake percentage.
        """
        return self.calorie_intake * 100 / self.tdee

    @property
    def calorie_deficit(self) -> Decimal:
        """Get calorie deficit.

        Returns:
             Decimal: calorie deficit.
        """
        return self.tdee - self.calorie_intake

    @property
    def protein_intake_g(self) -> Decimal:
        """Get protein intake in grams.

        Returns:
            Decimal: protein intake in grams.
        """
        grams = Decimal(0)
        for food in self.foods.all():
            grams += food.protein_g
        return grams
