"""Week model module."""


from decimal import Decimal

from django.db import models

from apps.libs.basemodel import BaseModel


class WeekPlan(BaseModel):
    """WeekPlan model class."""

    PLAN_LENGTH_DAYS = 7
    # The following represent percentages. They should all sum 700
    DEFICIT_DISTRIBUTION = [110, 110, 110, 110, 90, 80, 90]
    EXERCISE_RATE = Decimal("1.375")

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
        help_text="Protein grams consumed per kilo of body weight",
    )

    fat_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        verbose_name="Fat (%)",
        help_text="Fat percentage of the total calorie goal.",
    )

    deficit = models.PositiveIntegerField(
        default=0,
        verbose_name="Deficit (kcals/day)",
        help_text=(
            "This deficit is the average per day. It might be different on "
            "each day of the week if the distribution is not even."
        ),
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"Week {self.start_date.isocalendar().week}"

    def extra_surplus(self, day_num: int) -> Decimal:
        """Calculate extra surplus for the day based on the previous days.

        Args:
            day_num (int): day number.

        Returns:
            Decimal: surplus
        """
        surplus = Decimal("0")
        for day in self.days.filter(day_num__lt=day_num):
            surplus += day.calorie_surplus
        return surplus / (self.PLAN_LENGTH_DAYS - day_num + 1)

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
    def calorie_goal(self) -> Decimal:
        """Get calorie goal.

        Returns:
            Decimal: calorie goal.
        """
        goal = Decimal("0")
        for day in self.days.all():
            goal += day.calorie_goal
        return goal

    # Intake
    @property
    def calories(self) -> Decimal:
        """Get calorie intake.

        Returns:
            Decimal: calorie intake.
        """
        kcals = Decimal("0")
        for day in self.days.all():
            kcals += day.calories
        return kcals

    @property
    def calorie_intake_perc(self) -> Decimal:
        """Get calorie intake percentage.

        Returns:
            Decimal: calorie intake percentage.
        """
        if not self.calorie_goal:
            return Decimal("0")

        return self.calories * 100 / self.calorie_goal

    @property
    def calorie_deficit(self) -> Decimal:
        """Get calorie deficit.

        Returns:
            Decimal: calorie deficit.
        """
        return self.twee - self.calories
