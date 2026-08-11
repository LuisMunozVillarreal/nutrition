"""GraphQL Schema Configuration."""

# pylint: disable=too-few-public-methods

from datetime import datetime, timedelta, timezone
from typing import Any

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
from apps.libs.graphql import get_request_user
from apps.measurements.models import Measurement
from apps.measurements.schema import MeasurementMutation, MeasurementQuery
from apps.plans.models import Day
from apps.plans.schema import PlanMutation, PlanQuery
from config.middleware import authenticated_request_user

User = get_user_model()


def authenticated_session_user(context: Any) -> Any:
    """Resolve a possibly lazy Django session user synchronously.

    Args:
        context: Strawberry GraphQL request context.

    Returns:
        The authenticated Django session user, or None.
    """
    return get_request_user(context)


def authenticated_user(context: Any) -> Any:
    """Return the bearer user, falling back to the session user.

    Args:
        context: Strawberry GraphQL request context.

    Returns:
        The authenticated Django user, or None.
    """
    if context is None:
        return None

    request = getattr(context, "request", context)
    return authenticated_request_user(request)


@strawberry.type
class DashboardMeasurement:
    """A bounded measurement point for the dashboard trend."""

    id: strawberry.ID
    weight: float
    body_fat_perc: float | None
    created_at: str


@strawberry.type
class DashboardNutrition:
    """The current user's nutrition totals for one local calendar day."""

    id: strawberry.ID
    day: str
    energy_kcal: float
    energy_kcal_goal: float
    intake_count: int


@strawberry.type
class DashboardData:
    """Dashboard specific data."""

    latest_weight: float | None
    latest_body_fat: float | None
    goal_body_fat: float | None
    recent_measurements: list[DashboardMeasurement]
    today_nutrition: DashboardNutrition | None


@strawberry.type
class UserType:
    """GraphQL User Type."""

    id: strawberry.ID
    email: str
    first_name: str
    last_name: str
    is_staff: bool

    @strawberry.field
    def dashboard(self, timezone_offset_minutes: int = 0) -> DashboardData:
        """Get dashboard data.

        Args:
            timezone_offset_minutes: Browser offset from UTC in minutes.

        Returns:
            DashboardData: Dashboard data object
        """
        measurements = list(
            Measurement.objects.filter(user_id=self.id).order_by(
                "-created_at", "-id"
            )[:14]
        )
        measurement = measurements[0] if measurements else None
        goal = (
            User.objects.get(pk=self.id)
            .fat_perc_goals.order_by("-created_at", "-id")  # type: ignore
            .first()
        )

        safe_offset = max(-14 * 60, min(14 * 60, timezone_offset_minutes))
        local_today = (
            datetime.now(timezone.utc) - timedelta(minutes=safe_offset)
        ).date()
        today = (
            Day.objects.filter(plan__user_id=self.id, day=local_today)
            .order_by("-plan__start_date", "-plan_id")
            .first()
        )

        return DashboardData(
            latest_weight=float(measurement.weight) if measurement else None,
            latest_body_fat=(
                float(measurement.calculation_body_fat_perc)
                if measurement
                and measurement.calculation_body_fat_perc is not None
                else None
            ),
            goal_body_fat=float(goal.body_fat_perc) if goal else None,
            recent_measurements=[
                DashboardMeasurement(
                    id=strawberry.ID(str(item.id)),
                    weight=float(item.weight),
                    body_fat_perc=(
                        float(item.body_fat_perc)
                        if item.body_fat_perc is not None
                        else None
                    ),
                    created_at=item.created_at.isoformat(),
                )
                for item in reversed(measurements)
            ],
            today_nutrition=(
                DashboardNutrition(
                    id=strawberry.ID(str(today.id)),
                    day=today.day.isoformat(),
                    energy_kcal=float(today.energy_kcal),
                    energy_kcal_goal=float(today.energy_kcal_goal),
                    intake_count=today.intakes.count(),
                )
                if today
                else None
            ),
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
        user = authenticated_user(info.context)
        if user is None:
            return None
        # Explicit conversion to UserType
        return UserType(
            id=strawberry.ID(str(user.id)),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            is_staff=user.is_staff,
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
                    "exp": datetime.now(timezone.utc) + timedelta(days=7),
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
                    is_staff=user.is_staff,
                ),
            )
        raise ValueError("Invalid credentials")


schema = strawberry.Schema(query=Query, mutation=Mutation)
