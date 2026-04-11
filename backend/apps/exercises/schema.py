"""Exercises GraphQL schema module."""

# pylint: disable=too-few-public-methods

from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.exercises.models import DaySteps, Exercise


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
            duration=str(obj.duration) if obj.duration else None,
            distance=(float(obj.distance) if obj.distance else None),
            created_at=obj.created_at.isoformat(),
        )


@strawberry.type
class DayStepsType:
    """GraphQL DaySteps Type."""

    id: strawberry.ID
    day_id: int
    steps: int
    kcals: float
    created_at: str

    @staticmethod
    def from_model(obj: DaySteps) -> "DayStepsType":
        """Create DayStepsType from model instance.

        Args:
            obj (DaySteps): the model instance.

        Returns:
            DayStepsType: the GraphQL type.
        """
        return DayStepsType(
            id=strawberry.ID(str(obj.id)),
            day_id=obj.day_id,
            steps=obj.steps,
            kcals=float(obj.kcals),
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return []

        return [
            DayStepsType.from_model(ds)
            for ds in DaySteps.objects.filter(
                day__plan__user=user,
            ).order_by("-day__day")
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = DaySteps.objects.get(pk=id, day__plan__user=user)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        import datetime

        from apps.plans.models import Day

        try:
            day = Day.objects.get(pk=day_id, plan__user=user)
        except Day.DoesNotExist as e:
            raise ValueError("Day not found") from e

        parsed_duration = None
        if duration:
            parts = duration.split(":")
            parsed_duration = datetime.timedelta(
                hours=int(parts[0]),
                minutes=int(parts[1]),
                seconds=int(parts[2]) if len(parts) > 2 else 0,
            )

        obj = Exercise.objects.create(
            day=day,
            time=datetime.time.fromisoformat(time),
            type=type,
            kcals=kcals,
            duration=parsed_duration,
            distance=(Decimal(str(distance)) if distance else None),
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
        import datetime

        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Exercise.objects.get(pk=id, day__plan__user=user)
        except Exercise.DoesNotExist as e:
            raise ValueError("Exercise not found") from e

        obj.time = datetime.time.fromisoformat(time)
        obj.type = type
        obj.kcals = kcals

        if duration:
            parts = duration.split(":")
            obj.duration = datetime.timedelta(
                hours=int(parts[0]),
                minutes=int(parts[1]),
                seconds=int(parts[2]) if len(parts) > 2 else 0,
            )
        else:
            obj.duration = None

        obj.distance = Decimal(str(distance)) if distance else None
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        from apps.plans.models import Day

        try:
            day = Day.objects.get(pk=day_id, plan__user=user)
        except Day.DoesNotExist as e:
            raise ValueError("Day not found") from e

        obj = DaySteps.objects.create(day=day, steps=steps)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = DaySteps.objects.get(pk=id, day__plan__user=user)
        except DaySteps.DoesNotExist as e:
            raise ValueError("Day steps not found") from e

        obj.steps = steps
        obj.save()
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = DaySteps.objects.get(pk=id, day__plan__user=user)
        except DaySteps.DoesNotExist as e:
            raise ValueError("Day steps not found") from e

        obj.delete()
        return True
