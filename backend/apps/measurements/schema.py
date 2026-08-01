"""Measurements GraphQL schema module."""

# pylint: disable=too-few-public-methods

from decimal import Decimal

import strawberry
from django.db import router, transaction
from strawberry.types import Info

from apps.libs.graphql import (
    get_request_user,
    validated_percentage_decimal,
    validated_positive_decimal,
)
from apps.measurements.models import Measurement
from apps.plans.locks import lock_plan_aggregate_rows
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
    def latest_measurement(self, info: Info) -> MeasurementType | None:
        """Get the newest measurement for the current user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            MeasurementType | None: newest measurement or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        measurement = (
            Measurement.objects.filter(user=user)
            .order_by("-created_at", "-id")
            .first()
        )
        return MeasurementType.from_model(measurement) if measurement else None

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
                body_fat_perc,
                "bodyFatPerc",
                Measurement._meta.get_field("body_fat_perc"),
            ),
            weight=validated_positive_decimal(
                weight, "weight", Measurement._meta.get_field("weight")
            ),
        )
        return MeasurementType.from_model(obj)

    @strawberry.mutation
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
            body_fat_perc,
            "bodyFatPerc",
            Measurement._meta.get_field("body_fat_perc"),
        )
        validated_weight = validated_positive_decimal(
            weight, "weight", Measurement._meta.get_field("weight")
        )
        using = router.db_for_write(Measurement, instance=user)
        with transaction.atomic(using=using):
            try:
                obj = (
                    Measurement.objects.using(using)
                    .select_for_update()
                    .get(pk=id, user=user)
                )
            except Measurement.DoesNotExist as e:
                raise ValueError("Measurement not found") from e

            plan_ids = tuple(
                WeekPlan.objects.using(using)
                .filter(measurement=obj)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            day_ids = tuple(
                Day.objects.using(using)
                .filter(plan_id__in=plan_ids)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            aggregate_locks = lock_plan_aggregate_rows(
                using=using,
                plan_ids=plan_ids,
                day_ids=day_ids,
            )
            plans = aggregate_locks.plans
            days = aggregate_locks.days
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

            try:
                obj.body_fat_perc = validated_body_fat_perc
                obj.weight = validated_weight
                obj.save(using=using)
                for day in days:
                    day.save(using=using)
            finally:
                aggregate_locks.clear_markers()
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
