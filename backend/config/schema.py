"""GraphQL Schema Configuration."""

# pylint: disable=too-few-public-methods

from datetime import datetime, timedelta, timezone

import jwt
import strawberry
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from strawberry.types import Info

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
        """Get dashboard data."""
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
class Query:
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
        user = info.context.user
        if not user.is_authenticated:
            return None
        # Explicit conversion to UserType
        return UserType(
            id=strawberry.ID(str(user.id)),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
        )


@strawberry.type
class Mutation:
    """Root Mutation."""

    @strawberry.mutation
    async def login(self, email: str, password: str) -> AuthPayload:
        """Authenticate user and return token.

        Args:
            email (str): User email
            password (str): User password

        Returns:
            AuthPayload: Content with token and user info

        Raises:
            ValueError: If credentials are invalid
        """
        user = await sync_to_async(authenticate)(
            username=email, password=password
        )
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
