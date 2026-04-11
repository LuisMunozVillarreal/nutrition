"""GraphQL Schema Configuration."""

# pylint: disable=too-few-public-methods

from datetime import datetime, timedelta, timezone

import jwt
import strawberry
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from strawberry.types import Info

from apps.exercises.schema import ExerciseMutation, ExerciseQuery
from apps.foods.schema import (
    CupboardMutation,
    CupboardQuery,
    FoodMutation,
    FoodQuery,
    RecipeMutation,
    RecipeQuery,
)
from apps.goals.schema import GoalMutation, GoalQuery
from apps.measurements.schema import MeasurementMutation, MeasurementQuery
from apps.plans.schema import PlanMutation, PlanQuery

User = get_user_model()


@strawberry.type
class DashboardData:
    """Dashboard specific data."""

    latest_weight: float | None
    latest_body_fat: float | None
    goal_body_fat: float | None


@strawberry.type
class UserType:
    """GraphQL User Type."""

    id: strawberry.ID
    email: str
    first_name: str
    last_name: str

    @strawberry.field
    def dashboard(self) -> DashboardData:
        """Get dashboard data.

        Returns:
            DashboardData: Dashboard data object
        """
        # pylint: disable=no-member
        # self is the UserType instance or the User model depending on how it
        # was returned.
        # But for Mypy, it treats it as UserType.
        # We need to fetch the actual user model to get relations safely.
        # Since self.id is available, we can query.
        # However, at runtime 'self' IS the User model if returned from 'me'.
        # To satisfy mypy, casting or fresh query is needed.
        # Let's use the ID to be safe and clear.

        user_model = User.objects.get(pk=self.id)
        measurement = user_model.measurements.last()  # type: ignore
        goal = user_model.fat_perc_goals.last()  # type: ignore

        return DashboardData(
            latest_weight=float(measurement.weight) if measurement else None,
            latest_body_fat=(
                float(measurement.body_fat_perc) if measurement else None
            ),
            goal_body_fat=float(goal.body_fat_perc) if goal else None,
        )


@strawberry.type
class AuthPayload:
    """Authentication Payload."""

    token: str
    user: UserType


@strawberry.type
class Query(
    MeasurementQuery,
    GoalQuery,
    ExerciseQuery,
    PlanQuery,
    FoodQuery,
    RecipeQuery,
    CupboardQuery,
):
    """Root Query."""

    @strawberry.field
    def hello(self) -> str:
        """Return hello world string.

        Returns:
            str: Hello world
        """
        return "world"

    @strawberry.field
    def me(self, info: Info) -> UserType | None:
        """Return current user info.

        Args:
            info: GraphQL execution info

        Returns:
            UserType | None: Current user or None
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        # Explicit conversion to UserType
        return UserType(
            id=strawberry.ID(str(user.id)),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
        )


@strawberry.type
class Mutation(
    MeasurementMutation,
    GoalMutation,
    ExerciseMutation,
    PlanMutation,
    FoodMutation,
    RecipeMutation,
    CupboardMutation,
):
    """Root Mutation."""

    @strawberry.mutation
    def login(self, email: str, password: str) -> AuthPayload:
        """Authenticate user and return token.

        Args:
            email (str): User email
            password (str): User password

        Returns:
            AuthPayload: Content with token and user info

        Raises:
            ValueError: If credentials are invalid
        """
        user = authenticate(username=email, password=password)
        if user is not None:

            token = jwt.encode(
                {
                    "sub": str(user.id),
                    "exp": datetime.now(timezone.utc) + timedelta(days=1),
                },
                settings.SECRET_KEY,
                algorithm="HS256",
            )

            return AuthPayload(
                token=token,
                user=UserType(
                    id=strawberry.ID(str(user.id)),
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                ),
            )
        raise ValueError("Invalid credentials")


schema = strawberry.Schema(query=Query, mutation=Mutation)
