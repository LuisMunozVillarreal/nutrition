"""goals app models module."""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.libs.basemodel import BaseModel

WEEKS_PER_MONTH = 4
WEEKS_PER_YEAR = 52


class FatPercGoal(BaseModel):
    """FatPercGoal model class."""

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="fat_perc_goals",
    )

    body_fat_perc = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        help_text="Body fat percentage goal.",
    )

    def get_weeks_to_goal(self, cutting_kcals_week: int) -> Decimal:
        """Get weeks to goal.

        Args:
            cutting_kcals_week (int): cutting kcals per week.

        Returns:
            Decimal: weeks to goal.
        """
        # pylint: disable-next=no-member
        measurement = self.user.measurements.last()
        if not measurement:
            return Decimal("0")

        body_fat_perc = measurement.body_fat_perc
        fat_kg = measurement.fat_kg

        fat_kg_goal = self.body_fat_perc * fat_kg / body_fat_perc
        fat_kcal_to_cut = fat_kg_goal * settings.KCAL_KG

        return fat_kcal_to_cut / cutting_kcals_week

    def get_months_to_goal(self, cutting_kcals_week: int) -> Decimal:
        """Get weeks to goal.

        Args:
            cutting_kcals_week (int): cutting kcals per week.

        Returns:
            Decimal: weeks to goal.
        """
        return self.get_weeks_to_goal(cutting_kcals_week) / WEEKS_PER_MONTH

    def get_years_to_goal(self, cutting_kcals_week: int) -> Decimal:
        """Get years to goal.

        Args:
            cutting_kcals_week (int): cutting kcals per week.

        Returns:
            Decimal: years to goal.
        """
        return self.get_weeks_to_goal(cutting_kcals_week) / WEEKS_PER_YEAR

    def get_goal_hit_date(self, cutting_kcals_week: int) -> date:
        """Get goal hit date.

        Args:
            cutting_kcals_week (int): cutting kcals per week.

        Returns:
            date: goal hit date.
        """
        return date.today() + timedelta(
            weeks=int(self.get_weeks_to_goal(cutting_kcals_week))
        )
