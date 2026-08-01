"""GraphQL Schema Configuration."""

# pylint: disable=too-few-public-methods

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any

import jwt
import strawberry
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import router
from django.utils import timezone
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
from apps.garmin.models import (
    GARMIN_PROVIDER,
    GarminConnection,
    GarminOAuthState,
)
from apps.garmin.services import (
    begin_authorization,
    exchange_code_for_tokens,
    revoke_refresh_token,
)
from apps.goals.schema import GoalMutation, GoalQuery
from apps.libs.graphql import get_request_user
from apps.measurements.models import Measurement
from apps.measurements.schema import MeasurementMutation, MeasurementQuery
from apps.plans.models import Day
from apps.plans.schema import PlanMutation, PlanQuery
from config.middleware import authenticated_request_user

User = get_user_model()


@strawberry.type
class GarminSyncSummaryType:
    """Garmin synchronization output summary."""

    imported: int
    duplicates: int
    unsupported: int
    invalid: int


@strawberry.type
class GarminAuthStart:
    """OAuth start payload returned from Garmin begin."""

    authorization_url: str
    state: str
    expires_at: str


@strawberry.type
class GarminStatus:
    """Garmin status object for a user."""

    enabled: bool
    connected: bool
    has_refresh_token: bool
    last_synced_at: str | None
    last_sync_summary: GarminSyncSummaryType | None


@strawberry.type
class GarminQuery:
    """Query mixin for Garmin integration state."""

    @strawberry.field
    def garmin_status(self, info: Info) -> GarminStatus | None:
        """Return Garmin status for the current request user."""
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        connection = GarminConnection.objects.filter(user=user).first()
        if connection is None:
            return GarminStatus(
                enabled=bool(settings.GARMIN_ENABLED),
                connected=False,
                has_refresh_token=False,
                last_synced_at=None,
                last_sync_summary=None,
            )

        return GarminStatus(
            enabled=bool(settings.GARMIN_ENABLED),
            connected=connection.is_connected,
            has_refresh_token=connection.has_refresh_token,
            last_synced_at=(
                connection.last_synced_at.isoformat()
                if connection.last_synced_at
                else None
            ),
            last_sync_summary=(
                GarminSyncSummaryType(
                    imported=connection.last_sync_summary.get("imported", 0),
                    duplicates=connection.last_sync_summary.get(
                        "duplicates", 0
                    ),
                    unsupported=connection.last_sync_summary.get(
                        "unsupported", 0
                    ),
                    invalid=connection.last_sync_summary.get("invalid", 0),
                )
                if connection.last_sync_summary
                else None
            ),
        )


@strawberry.type
class GarminMutation:
    """Mutation mixin for Garmin OAuth lifecycle."""

    @strawberry.mutation
    def begin_garmin_authorization(self, info: Info) -> GarminAuthStart:
        """Create a one-time state and return an authorization URL."""
        user = authenticated_bearer_user(info.context)
        if user is None:
            raise PermissionError("Authentication required")

        authorization_url, expires_at, state = begin_authorization(user)
        return GarminAuthStart(
            authorization_url=authorization_url,
            state=state,
            expires_at=expires_at.isoformat(),
        )

    @strawberry.mutation
    def complete_garmin_authorization(
        self,
        info: Info,
        code: str,
        state: str,
    ) -> GarminStatus:
        """Complete OAuth and persist Garmin credentials for the caller."""
        user = authenticated_bearer_user(info.context)
        if user is None:
            raise PermissionError("Authentication required")

        if not state:
            raise ValueError("state is required")
        if not code:
            raise ValueError("code is required")

        from django.db import transaction

        using = router.db_for_write(GarminConnection, instance=user)
        connection_pk: int | None
        expected_generation: int
        expected_status: str
        expected_provider_account_id: str

        with transaction.atomic(using=using):
            connection, created_connection = GarminConnection.objects.using(
                using
            ).get_or_create(
                user=user,
                defaults={
                    "provider": GARMIN_PROVIDER,
                    "status": GarminConnection.Status.DISCONNECTED,
                },
            )
            connection = (
                GarminConnection.objects.using(using)
                .select_for_update()
                .get(pk=connection.pk)
            )
            expected_generation = connection.connection_generation
            expected_status = connection.status
            expected_provider_account_id = connection.provider_account_id
            connection_pk = connection.pk

            GarminOAuthState.consume_for_user(
                user=user,
                raw_state=state,
                provider=GARMIN_PROVIDER,
                using=using,
            )

        try:
            token_pair = exchange_code_for_tokens(code)
        except Exception as exc:
            if created_connection:
                with transaction.atomic(using=using):
                    placeholder = (
                        GarminConnection.objects.using(using)
                        .select_for_update()
                        .filter(pk=connection_pk)
                        .first()
                    )
                    if (
                        placeholder is not None
                        and placeholder.connection_generation
                        == expected_generation
                        and placeholder.status == expected_status
                        and placeholder.provider_account_id
                        == expected_provider_account_id
                        and not placeholder.access_token_encrypted
                        and not placeholder.refresh_token_encrypted
                    ):
                        placeholder.delete(using=using)
            raise ValueError(
                "Garmin connection state changed during authorization"
            ) from exc

        with transaction.atomic(using=using):
            connection = (
                GarminConnection.objects.using(using)
                .select_for_update()
                .get(pk=connection_pk)
            )
            if (
                connection.connection_generation != expected_generation
                or connection.status != expected_status
                or connection.provider_account_id
                != expected_provider_account_id
            ):
                raise ValueError(
                    "Garmin connection state changed during authorization"
                )

            if connection.provider != GARMIN_PROVIDER:
                connection.provider = GARMIN_PROVIDER
            previous_account = connection.provider_account_id
            connection.set_tokens(token_pair, expires_in=token_pair.expires_in)
            if (
                previous_account
                and token_pair.provider_account_id
                and token_pair.provider_account_id != previous_account
            ):
                connection.last_sync_summary = {}
                connection.last_synced_at = None

            updated_rows = (
                GarminConnection.objects.using(using)
                .filter(pk=connection.pk)
                .update(
                    provider=connection.provider,
                    provider_account_id=connection.provider_account_id,
                    provider_scopes=connection.provider_scopes,
                    access_token_encrypted=connection.access_token_encrypted,
                    refresh_token_encrypted=connection.refresh_token_encrypted,
                    access_token_expires_at=connection.access_token_expires_at,
                    status=connection.status,
                    connection_generation=connection.connection_generation,
                    last_synced_at=connection.last_synced_at,
                    last_sync_summary=connection.last_sync_summary,
                    updated_at=timezone.now(),
                )
            )
            if updated_rows != 1:
                raise ValueError(
                    "Garmin connection state changed during authorization"
                )

        return GarminStatus(
            enabled=bool(settings.GARMIN_ENABLED),
            connected=connection.is_connected,
            has_refresh_token=connection.has_refresh_token,
            last_synced_at=None,
            last_sync_summary=None,
        )

    @strawberry.mutation
    def disconnect_garmin(self, info: Info) -> bool:
        """Disconnect a Garmin connection by erasing stored secrets."""
        user = authenticated_bearer_user(info.context)
        if user is None:
            raise PermissionError("Authentication required")
        using = router.db_for_write(GarminConnection, instance=user)
        from django.db import transaction

        with transaction.atomic(using=using):
            try:
                connection = (
                    GarminConnection.objects.using(using)
                    .select_for_update()
                    .get(
                        user=user,
                    )
                )
            except GarminConnection.DoesNotExist:
                return False

            raw_refresh_token = connection.refresh_token_encrypted

            connection.clear_tokens()
            connection.save(
                using=using,
                update_fields=[
                    "access_token_encrypted",
                    "refresh_token_encrypted",
                    "provider_scopes",
                    "provider_account_id",
                    "provider",
                    "access_token_expires_at",
                    "status",
                    "connection_generation",
                    "last_synced_at",
                    "last_sync_summary",
                    "updated_at",
                ],
            )

        if raw_refresh_token:
            try:
                refresh_token = GarminConnection._decrypt_value(
                    raw_refresh_token
                )
            except (ImproperlyConfigured, ValueError):
                refresh_token = ""
            if refresh_token:
                try:
                    revoke_refresh_token(refresh_token)
                except Exception:
                    pass

        return True


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


def authenticated_bearer_user(context: Any) -> Any:
    """Return bearer user for sensitive Garmin operations."""
    request = getattr(context, "request", context)
    if request is None:
        return None

    auth_header = getattr(request, "META", {}).get("HTTP_AUTHORIZATION", "")
    if not isinstance(auth_header, str):
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return authenticated_user(context)


@strawberry.type
class DashboardMeasurement:
    """A bounded measurement point for the dashboard trend."""

    id: strawberry.ID
    weight: float
    body_fat_perc: float
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
                float(measurement.body_fat_perc) if measurement else None
            ),
            goal_body_fat=float(goal.body_fat_perc) if goal else None,
            recent_measurements=[
                DashboardMeasurement(
                    id=strawberry.ID(str(item.id)),
                    weight=float(item.weight),
                    body_fat_perc=float(item.body_fat_perc),
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
    GarminQuery,
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
    GarminMutation,
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
                    "exp": datetime.now(dt_timezone.utc) + timedelta(days=1),
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
