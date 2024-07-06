"""goals app admin config module."""

from datetime import date
from decimal import Decimal

from django.contrib import admin

from .models import FatPercGoal


@admin.register(FatPercGoal)
class FatPercGoalAdmin(admin.ModelAdmin):
    """FatPercGoal admin config class."""

    list_display = [
        "id",
        "user",
        "body_fat_perc",
        "weeks_to_goal_at_2500kcals",
        "months_to_goal_at_2500kcals",
        "years_to_goal_at_2500kcals",
        "goal_hit_date_at_2500kcals",
    ]

    def weeks_to_goal_at_2500kcals(self, obj: FatPercGoal) -> Decimal:
        """Get weeks to goal at 2500 kcals.

        Args:
            obj (FatPercGoal): instance of the object.

        Returns:
            Decimal: weeks to goal at 2500 kcals.
        """
        return obj.get_weeks_to_goal(2500)

    def months_to_goal_at_2500kcals(self, obj: FatPercGoal) -> Decimal:
        """Months weeks to goal at 2500 kcals.

        Args:
            obj (FatPercGoal): instance of the object.

        Returns:
            Decimal: months to goal at 2500 kcals.
        """
        return obj.get_months_to_goal(2500)

    def years_to_goal_at_2500kcals(self, obj: FatPercGoal) -> Decimal:
        """Get years to goal at 2500 kcals.

        Args:
            obj (FatPercGoal): instance of the object.

        Returns:
            Decimal: years to goal at 2500 kcals.
        """
        return obj.get_years_to_goal(2500)

    def goal_hit_date_at_2500kcals(self, obj: FatPercGoal) -> date:
        """Get goal hit date at 2500 kcals.

        Args:
            obj (FatPercGoal): instance of the object.

        Returns:
            date: goal hit date at 2500 kcals.
        """
        return obj.get_goal_hit_date(2500)
