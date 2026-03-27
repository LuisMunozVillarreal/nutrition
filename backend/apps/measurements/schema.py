"""Measurements GraphQL schema module."""

# pylint: disable=too-few-public-methods

from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.measurements.models import Measurement


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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = Measurement.objects.create(
            user=user,
            body_fat_perc=Decimal(str(body_fat_perc)),
            weight=Decimal(str(weight)),
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Measurement.objects.get(pk=id, user=user)
        except Measurement.DoesNotExist as e:
            raise ValueError("Measurement not found") from e

        obj.body_fat_perc = Decimal(str(body_fat_perc))
        obj.weight = Decimal(str(weight))
        obj.save()
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Measurement.objects.get(pk=id, user=user)
        except Measurement.DoesNotExist as e:
            raise ValueError("Measurement not found") from e

        obj.delete()
        return True
