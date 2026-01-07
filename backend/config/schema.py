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
class UserType:
    """GraphQL User Type."""

    id: strawberry.ID
    email: str
    first_name: str
    last_name: str


@strawberry.type
class AuthPayload:
    """Authentication Payload."""

    token: str
    user: UserType


from apps.garmin.schema import Mutation as GarminMutation
from apps.garmin.schema import Query as GarminQuery

@strawberry.type
class Query(GarminQuery):
    """Root Query."""

    @strawberry.field
    def hello(self) -> str:
        """Return hello world string.

        Returns:
            str: Hello world
        """
        return "world"

    @strawberry.field
    def me(self, info: Info) -> str:  # pylint: disable=unused-argument
        """Return current user info (placeholder).

        Args:
            info: GraphQL execution info

        Returns:
            str: Placeholder message
        """
        # Placeholder for real auth check
        return "Not implemented fully yet"


@strawberry.type
class Mutation(GarminMutation):
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
