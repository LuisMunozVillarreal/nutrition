"""Exercises GraphQL schema module."""

# pylint: disable=too-few-public-methods

import datetime
import re
from decimal import Decimal

import strawberry
from django.core.exceptions import ObjectDoesNotExist
from strawberry.types import Info

from apps.exercises.models import DaySteps, Exercise
from apps.libs.graphql import (
    get_request_user,
    validated_decimal_field,
    validated_non_negative_decimal,
)

MAX_DISTANCE = Decimal("99999999.99")
MAX_DURATION_SECONDS = (2**63 - 1) // 1_000_000
DURATION_ERROR = (
    "duration must use HH:MM:SS with total hours and 00-59 minutes/seconds"
)
DURATION_PATTERN = re.compile(
    r"(?P<hours>(?:[0-9]{2}|[1-9][0-9]{2,})):"
    r"(?P<minutes>[0-5][0-9]):(?P<seconds>[0-5][0-9])"
)


def _parse_duration(value: str | None) -> datetime.timedelta | None:
    """Parse a canonical total-hours duration or raise a stable input error."""
    if value is None:
        return None

    match = DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(DURATION_ERROR)

    try:
        hours = int(match.group("hours"))
        minutes = int(match.group("minutes"))
        seconds = int(match.group("seconds"))
        total_seconds = hours * 3600 + minutes * 60 + seconds
        if total_seconds > MAX_DURATION_SECONDS:
            raise OverflowError
        return datetime.timedelta(seconds=total_seconds)
    except (OverflowError, ValueError):
        raise ValueError(DURATION_ERROR) from None


def _format_duration(value: datetime.timedelta | None) -> str | None:
    """Serialize a duration as total hours using canonical ``HH:MM:SS``."""
    if value is None:
        return None
    total_seconds = value.days * 86400 + value.seconds
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _validated_non_negative_int(value: int, field_name: str) -> int:
    """Return a non-negative integer or raise a stable input error."""
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


def _validated_exercise_values(
    exercise_type: str, kcals: int, distance: float | None
) -> tuple[str, int, Decimal | None]:
    """Validate exercise values shared by create and update mutations."""
    valid_types = [choice[0] for choice in Exercise.EXERCISE_CHOICES]
    if exercise_type not in valid_types:
        raise ValueError(f"type must be one of: {', '.join(valid_types)}")
    validated_kcals = _validated_non_negative_int(kcals, "kcals")

    validated_distance = None
    if distance is not None:
        validated_distance = validated_non_negative_decimal(
            distance, "distance"
        )
        exponent = validated_distance.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("distance must have at most 2 decimal places")
        if validated_distance > MAX_DISTANCE:
            raise ValueError(
                f"distance must be less than or equal to {MAX_DISTANCE}"
            )
        validated_distance = validated_decimal_field(
            validated_distance,
            "distance",
            Exercise._meta.get_field("distance"),
        )
    return exercise_type, validated_kcals, validated_distance


@strawberry.type
class ExerciseType:
    """GraphQL Exercise Type."""

    id: strawberry.ID
    day_id: int
    time: str
    type: str
    kcals: int
    duration: str | None
    distance: float | None
    created_at: str

    @staticmethod
    def from_model(obj: Exercise) -> "ExerciseType":
        """Create ExerciseType from model instance.

        Args:
            obj (Exercise): the model instance.

        Returns:
            ExerciseType: the GraphQL type.
        """
        return ExerciseType(
            id=strawberry.ID(str(obj.id)),
            day_id=obj.day_id,
            time=str(obj.time),
            type=obj.type,
            kcals=obj.kcals,
            duration=_format_duration(obj.duration),
            distance=(
                float(obj.distance) if obj.distance is not None else None
            ),
            created_at=obj.created_at.isoformat(),
        )


@strawberry.type
class DayStepsType:
    """GraphQL DaySteps Type."""

    id: strawberry.ID
    day_id: int
    steps: int
    kcals: float
    source: str
    synced_at: str | None
    created_at: str

    @staticmethod
    def from_model(obj: DaySteps) -> "DayStepsType":
        """Create DayStepsType from model instance.

        Args:
            obj (DaySteps): the model instance.

        Returns:
            DayStepsType: the GraphQL type.
        """
        try:
            step_import = obj.step_import
        except ObjectDoesNotExist:
            step_import = None

        return DayStepsType(
            id=strawberry.ID(str(obj.id)),
            day_id=obj.day_id,
            steps=obj.steps,
            kcals=float(obj.kcals),
            source=(
                step_import.source
                if step_import is not None and step_import.is_active
                else "manual"
            ),
            synced_at=(
                step_import.observed_at.isoformat()
                if step_import is not None and step_import.is_active
                else None
            ),
            created_at=obj.created_at.isoformat(),
        )


@strawberry.type
class ExerciseQuery:
    """Exercise queries."""

    @strawberry.field
    def exercises(self, info: Info) -> list[ExerciseType]:
        """Get all exercises for the current user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[ExerciseType]: list of exercises.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []

        return [
            ExerciseType.from_model(e)
            for e in Exercise.objects.filter(
                day__plan__user=user,
            ).order_by("-day__day", "-time")
        ]

    @strawberry.field
    def exercise(self, info: Info, id: strawberry.ID) -> ExerciseType | None:
        """Get a single exercise by ID.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): exercise ID.

        Returns:
            ExerciseType | None: the exercise or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = Exercise.objects.get(pk=id, day__plan__user=user)
        except Exercise.DoesNotExist:
            return None

        return ExerciseType.from_model(obj)

    @strawberry.field
    def day_steps_list(self, info: Info) -> list[DayStepsType]:
        """Get all day steps for the current user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[DayStepsType]: list of day steps.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []

        return [
            DayStepsType.from_model(ds)
            for ds in DaySteps.objects.filter(
                day__plan__user=user,
            )
            .select_related("step_import")
            .order_by("-day__day")
        ]

    @strawberry.field
    def day_steps(self, info: Info, id: strawberry.ID) -> DayStepsType | None:
        """Get a single day steps record by ID.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): day steps ID.

        Returns:
            DayStepsType | None: the day steps or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = DaySteps.objects.select_related("step_import").get(
                pk=id,
                day__plan__user=user,
            )
        except DaySteps.DoesNotExist:
            return None

        return DayStepsType.from_model(obj)


@strawberry.type
class ExerciseMutation:
    """Exercise mutations."""

    @strawberry.mutation
    def create_exercise(
        self,
        info: Info,
        day_id: int,
        type: str,
        kcals: int,
        time: str = "00:00",
        duration: str | None = None,
        distance: float | None = None,
    ) -> ExerciseType:
        """Create a new exercise.

        Args:
            info (Info): GraphQL execution info.
            day_id (int): day ID.
            type (str): exercise type.
            kcals (int): calories burned.
            time (str): time of exercise.
            duration (str | None): duration.
            distance (float | None): distance in km.

        Returns:
            ExerciseType: the created exercise.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if day not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        validated_type, validated_kcals, validated_distance = (
            _validated_exercise_values(type, kcals, distance)
        )
        parsed_time = datetime.time.fromisoformat(time)
        parsed_duration = _parse_duration(duration)

        from apps.plans.models import Day

        try:
            day = Day.objects.get(pk=day_id, plan__user=user)
        except Day.DoesNotExist as e:
            raise ValueError("Day not found") from e

        obj = Exercise.objects.create(
            day=day,
            time=parsed_time,
            type=validated_type,
            kcals=validated_kcals,
            duration=parsed_duration,
            distance=validated_distance,
        )
        return ExerciseType.from_model(obj)

    @strawberry.mutation
    def update_exercise(
        self,
        info: Info,
        id: strawberry.ID,
        type: str,
        kcals: int,
        time: str = "00:00",
        duration: str | None = None,
        distance: float | None = None,
    ) -> ExerciseType:
        """Update an existing exercise.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): exercise ID.
            type (str): exercise type.
            kcals (int): calories burned.
            time (str): time of exercise.
            duration (str | None): duration.
            distance (float | None): distance in km.

        Returns:
            ExerciseType: the updated exercise.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if exercise not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        validated_type, validated_kcals, validated_distance = (
            _validated_exercise_values(type, kcals, distance)
        )
        parsed_time = datetime.time.fromisoformat(time)
        parsed_duration = _parse_duration(duration)

        try:
            obj = Exercise.objects.get(pk=id, day__plan__user=user)
        except Exercise.DoesNotExist as e:
            raise ValueError("Exercise not found") from e

        obj.time = parsed_time
        obj.type = validated_type
        obj.kcals = validated_kcals
        obj.duration = parsed_duration
        obj.distance = validated_distance
        obj.save()
        return ExerciseType.from_model(obj)

    @strawberry.mutation
    def delete_exercise(self, info: Info, id: strawberry.ID) -> bool:
        """Delete an exercise.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): exercise ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if exercise not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Exercise.objects.get(pk=id, day__plan__user=user)
        except Exercise.DoesNotExist as e:
            raise ValueError("Exercise not found") from e

        obj.delete()
        return True

    @strawberry.mutation
    def create_day_steps(
        self,
        info: Info,
        day_id: int,
        steps: int,
    ) -> DayStepsType:
        """Create a day steps record.

        Args:
            info (Info): GraphQL execution info.
            day_id (int): day ID.
            steps (int): number of steps.

        Returns:
            DayStepsType: the created day steps.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if day not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")
        validated_steps = _validated_non_negative_int(steps, "steps")

        from apps.health_sync.services import create_manual_day_steps

        obj = create_manual_day_steps(user, day_id, validated_steps)
        return DayStepsType.from_model(obj)

    @strawberry.mutation
    def update_day_steps(
        self,
        info: Info,
        id: strawberry.ID,
        steps: int,
    ) -> DayStepsType:
        """Update a day steps record.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): day steps ID.
            steps (int): number of steps.

        Returns:
            DayStepsType: the updated day steps.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if day steps not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")
        validated_steps = _validated_non_negative_int(steps, "steps")

        from apps.health_sync.services import update_manual_day_steps

        obj = update_manual_day_steps(user, int(id), validated_steps)
        return DayStepsType.from_model(obj)

    @strawberry.mutation
    def delete_day_steps(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a day steps record.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): day steps ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if day steps not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        from apps.health_sync.services import delete_manual_day_steps

        delete_manual_day_steps(user, int(id))
        return True
