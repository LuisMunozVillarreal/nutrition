"""Shared validation of plan parameters and derived nutrition goals."""

from decimal import Decimal

from django.conf import settings

from apps.libs.graphql import (
    validated_non_negative_decimal,
    validated_percentage_decimal,
    validated_positive_decimal,
)
from apps.measurements.models import Measurement
from apps.plans.models import WeekPlan


def validated_week_plan_parameters(
    measurement: Measurement,
    protein_g_kg: float,
    fat_perc: float,
    deficit: int,
    tdee_values: list[Decimal] | None = None,
    daily_deficits: list[Decimal] | None = None,
) -> tuple[Decimal, Decimal, int]:
    """Validate plan inputs and every resulting daily nutrition goal.

    Args:
        measurement (Measurement): Physiology used for the proposed goals.
        protein_g_kg (float): Protein grams per kilogram of body weight.
        fat_perc (float): Percentage of goal energy allocated to fat.
        deficit (int): Average daily energy deficit.
        tdee_values (list[Decimal] | None): Existing days' energy expenditure.
        daily_deficits (list[Decimal] | None): Existing days' actual deficits.

    Returns:
        tuple[Decimal, Decimal, int]: Validated protein, fat and deficit inputs.

    Raises:
        ValueError: If inputs or any resulting daily goal are invalid.
    """
    validated_protein_g_kg = validated_positive_decimal(
        protein_g_kg,
        "proteinGKg",
        WeekPlan._meta.get_field("protein_g_kg"),
    )
    validated_fat_perc = validated_percentage_decimal(
        fat_perc,
        "fatPerc",
        WeekPlan._meta.get_field("fat_perc"),
    )
    validated_deficit = validated_non_negative_decimal(deficit, "deficit")
    protein_g_goal = validated_protein_g_kg * measurement.weight
    daily_tdee_values = tdee_values or [
        measurement.bmr for _ in range(WeekPlan.PLAN_LENGTH_DAYS)
    ]
    daily_deficit_values = daily_deficits or [
        validated_deficit * Decimal(deficit_perc) / 100
        for deficit_perc in WeekPlan.DEFICIT_DISTRIBUTION
    ]

    if len(daily_tdee_values) != len(daily_deficit_values):
        raise ValueError("Every day must have a TDEE and deficit")

    for tdee, daily_deficit in zip(daily_tdee_values, daily_deficit_values):
        energy_kcal_goal = tdee - daily_deficit
        if not energy_kcal_goal.is_finite() or energy_kcal_goal <= 0:
            raise ValueError("energyKcalGoal must be greater than 0")
        fat_g_goal = (
            energy_kcal_goal
            * validated_fat_perc
            / 100
            / settings.FAT_KCAL_GRAM
        )
        carbs_g_goal = (
            energy_kcal_goal
            - fat_g_goal * settings.FAT_KCAL_GRAM
            - protein_g_goal * settings.PROTEIN_KCAL_GRAM
        ) / settings.CARB_KCAL_GRAM
        for field_name, goal in (
            ("proteinGGoal", protein_g_goal),
            ("fatGGoal", fat_g_goal),
            ("carbsGGoal", carbs_g_goal),
        ):
            if not goal.is_finite() or goal < 0:
                raise ValueError(
                    f"{field_name} must be greater than or equal to 0"
                )

    return validated_protein_g_kg, validated_fat_perc, int(validated_deficit)
