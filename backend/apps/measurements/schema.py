"""Measurements GraphQL schema module."""

# pylint: disable=too-few-public-methods

from decimal import Decimal

import strawberry
from django.db import transaction
from strawberry.types import Info

from apps.libs.graphql import (
    get_request_user,
    validated_percentage_decimal,
    validated_positive_decimal,
)
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from apps.plans.schema import _validated_week_plan_parameters


@strawberry.type
class MeasurementType:
    """GraphQL Measurement Type."""

    id: strawberry.ID
    body_fat_perc: float
    weight: float
    bmr: float
    fat_kg: float
    created_at: str

    @staticmethod
    def from_model(obj: Measurement) -> "MeasurementType":
        """Create MeasurementType from a Measurement model instance.

        Args:
            obj (Measurement): the model instance.

        Returns:
            MeasurementType: the GraphQL type.
        """
        return MeasurementType(
            id=strawberry.ID(str(obj.id)),
            body_fat_perc=float(obj.body_fat_perc),
            weight=float(obj.weight),
            bmr=float(obj.bmr),
            fat_kg=float(obj.fat_kg),
            created_at=obj.created_at.isoformat(),
        )


@strawberry.type
class MeasurementQuery:
    """Measurement queries."""

    @strawberry.field
    def measurements(self, info: Info) -> list[MeasurementType]:
        """Get all measurements for the current user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[MeasurementType]: list of measurements.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []

        return [
            MeasurementType.from_model(m)
            for m in Measurement.objects.filter(
                user=user,
            ).order_by("-created_at")
        ]

    @strawberry.field
    def measurement(
        self, info: Info, id: strawberry.ID
    ) -> MeasurementType | None:
        """Get a single measurement by ID.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): measurement ID.

        Returns:
            MeasurementType | None: the measurement or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = Measurement.objects.get(pk=id, user=user)
        except Measurement.DoesNotExist:
            return None

        return MeasurementType.from_model(obj)


@strawberry.type
class MeasurementMutation:
    """Measurement mutations."""

    @strawberry.mutation
    def create_measurement(
        self,
        info: Info,
        body_fat_perc: float,
        weight: float,
    ) -> MeasurementType:
        """Create a new measurement.

        Args:
            info (Info): GraphQL execution info.
            body_fat_perc (float): body fat percentage.
            weight (float): weight in kg.

        Returns:
            MeasurementType: the created measurement.

        Raises:
            PermissionError: if user is not authenticated.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = Measurement.objects.create(
            user=user,
            body_fat_perc=validated_percentage_decimal(
                body_fat_perc, "bodyFatPerc"
            ),
            weight=validated_positive_decimal(weight, "weight"),
        )
        return MeasurementType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_measurement(
        self,
        info: Info,
        id: strawberry.ID,
        body_fat_perc: float,
        weight: float,
    ) -> MeasurementType:
        """Update an existing measurement.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): measurement ID.
            body_fat_perc (float): body fat percentage.
            weight (float): weight in kg.

        Returns:
            MeasurementType: the updated measurement.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if measurement not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        validated_body_fat_perc = validated_percentage_decimal(
            body_fat_perc, "bodyFatPerc"
        )
        validated_weight = validated_positive_decimal(weight, "weight")
        try:
            obj = Measurement.objects.select_for_update().get(pk=id, user=user)
        except Measurement.DoesNotExist as e:
            raise ValueError("Measurement not found") from e

        plans = list(
            WeekPlan.objects.select_for_update()
            .filter(measurement=obj)
            .order_by("id")
        )
        days = list(
            Day.objects.select_for_update()
            .filter(plan__in=plans)
            .select_related("plan")
            .order_by("plan_id", "day_num")
        )
        proposed_measurement = Measurement(
            user=user,
            body_fat_perc=validated_body_fat_perc,
            weight=validated_weight,
        )
        for plan in plans:
            plan_days = [day for day in days if day.plan_id == plan.id]
            proposed_tdee_values = [
                (
                    proposed_measurement.bmr + day.neat + day.tef + day.eat
                    if day.tracked
                    else proposed_measurement.bmr * plan.EXERCISE_RATE
                )
                for day in plan_days
            ]
            _validated_week_plan_parameters(
                proposed_measurement,
                float(plan.protein_g_kg),
                float(plan.fat_perc),
                plan.deficit,
                proposed_tdee_values,
                [Decimal(day.deficit) for day in plan_days],
            )

        obj.body_fat_perc = validated_body_fat_perc
        obj.weight = validated_weight
        obj.save()
        for day in days:
            day.save()
        return MeasurementType.from_model(obj)

    @strawberry.mutation
    def delete_measurement(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a measurement.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): measurement ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if measurement not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Measurement.objects.get(pk=id, user=user)
        except Measurement.DoesNotExist as e:
            raise ValueError("Measurement not found") from e

        obj.delete()
        return True
