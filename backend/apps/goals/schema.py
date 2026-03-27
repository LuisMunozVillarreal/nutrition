"""Goals GraphQL schema module."""

# pylint: disable=too-few-public-methods

from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.goals.models import FatPercGoal


@strawberry.type
class FatPercGoalType:
    """GraphQL FatPercGoal Type."""

    id: strawberry.ID
    body_fat_perc: float
    created_at: str

    @staticmethod
    def from_model(obj: FatPercGoal) -> "FatPercGoalType":
        """Create FatPercGoalType from model instance.

        Args:
            obj (FatPercGoal): the model instance.

        Returns:
            FatPercGoalType: the GraphQL type.
        """
        return FatPercGoalType(
            id=strawberry.ID(str(obj.id)),
            body_fat_perc=float(obj.body_fat_perc),
            created_at=obj.created_at.isoformat(),
        )


@strawberry.type
class GoalQuery:
    """Goal queries."""

    @strawberry.field
    def fat_perc_goals(self, info: Info) -> list[FatPercGoalType]:
        """Get all fat percentage goals for the current user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[FatPercGoalType]: list of goals.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return []

        return [
            FatPercGoalType.from_model(g)
            for g in FatPercGoal.objects.filter(
                user=user,
            ).order_by("-created_at")
        ]

    @strawberry.field
    def fat_perc_goal(
        self, info: Info, id: strawberry.ID
    ) -> FatPercGoalType | None:
        """Get a single fat percentage goal by ID.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): goal ID.

        Returns:
            FatPercGoalType | None: the goal or None.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = FatPercGoal.objects.get(pk=id, user=user)
        except FatPercGoal.DoesNotExist:
            return None

        return FatPercGoalType.from_model(obj)


@strawberry.type
class GoalMutation:
    """Goal mutations."""

    @strawberry.mutation
    def create_fat_perc_goal(
        self,
        info: Info,
        body_fat_perc: float,
    ) -> FatPercGoalType:
        """Create a new fat percentage goal.

        Args:
            info (Info): GraphQL execution info.
            body_fat_perc (float): target body fat percentage.

        Returns:
            FatPercGoalType: the created goal.

        Raises:
            PermissionError: if user is not authenticated.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = FatPercGoal.objects.create(
            user=user,
            body_fat_perc=Decimal(str(body_fat_perc)),
        )
        return FatPercGoalType.from_model(obj)

    @strawberry.mutation
    def update_fat_perc_goal(
        self,
        info: Info,
        id: strawberry.ID,
        body_fat_perc: float,
    ) -> FatPercGoalType:
        """Update an existing fat percentage goal.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): goal ID.
            body_fat_perc (float): target body fat percentage.

        Returns:
            FatPercGoalType: the updated goal.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if goal not found.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = FatPercGoal.objects.get(pk=id, user=user)
        except FatPercGoal.DoesNotExist as e:
            raise ValueError("Goal not found") from e

        obj.body_fat_perc = Decimal(str(body_fat_perc))
        obj.save()
        return FatPercGoalType.from_model(obj)

    @strawberry.mutation
    def delete_fat_perc_goal(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a fat percentage goal.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): goal ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if goal not found.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = FatPercGoal.objects.get(pk=id, user=user)
        except FatPercGoal.DoesNotExist as e:
            raise ValueError("Goal not found") from e

        obj.delete()
        return True
