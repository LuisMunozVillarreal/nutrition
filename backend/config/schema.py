"""GraphQL Schema Configuration."""

# pylint: disable=too-few-public-methods

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any

import jwt
import strawberry
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.db import IntegrityError, router
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
    GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT,
    GarminConnection,
    GarminOAuthState,
    is_provider_account_ownership_conflict,
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


def _provider_account_switches_without_history(
    connection: GarminConnection,
    incoming_account_id: str | None,
    *,
    using: str,
) -> bool:
    """Validate account continuity and report a safe history-free switch."""
    historical_account_ids = list(
        connection.activities.using(using).values_list(
            "provider_account_id", flat=True
        )
    )
    previous_account_id = connection.provider_account_id
    if not historical_account_ids:
        return bool(
            previous_account_id
            and incoming_account_id
            and incoming_account_id != previous_account_id
        )

    known_historical_ids = {
        account_id for account_id in historical_account_ids if account_id
    }
    if previous_account_id:
        if known_historical_ids - {previous_account_id}:
            raise ValueError(
                "Garmin provider account cannot change while historical "
                "activities exist"
            )
        if incoming_account_id and incoming_account_id != previous_account_id:
            raise ValueError(
                "Garmin provider account cannot change while historical "
                "activities exist"
            )
        return False

    if len(known_historical_ids) == 1:
        historical_account_id = next(iter(known_historical_ids))
        if (
            not incoming_account_id
            or incoming_account_id == historical_account_id
        ):
            connection.provider_account_id = historical_account_id
            return False

    raise ValueError(
        "Garmin provider account cannot change while historical activities exist"
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
    def cancel_garmin_authorization(self, info: Info, state: str) -> bool:
        """Consume a provider-error callback state without token exchange."""
        user = authenticated_bearer_user(info.context)
        if user is None:
            raise PermissionError("Authentication required")

        error_message = "OAuth state is invalid or expired"
        if not state:
            raise ValueError(error_message)

        using = router.db_for_write(GarminOAuthState, instance=user)
        try:
            GarminOAuthState.consume_for_user(
                user=user,
                raw_state=state,
                provider=GARMIN_PROVIDER,
                using=using,
            )
        except (GarminOAuthState.DoesNotExist, ValueError) as exc:
            raise ValueError(error_message) from exc
        return True

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
        connection_pk: int
        attempt_generation: int
        expected_status: str
        expected_provider_account_id: str

        with transaction.atomic(using=using):
            connection, _ = GarminConnection.objects.using(
                using
            ).get_or_create(
                user=user,
                defaults={
                    "provider": GARMIN_PROVIDER,
                    "status": GarminConnection.Status.DISCONNECTED,
                    "authorization_placeholder": True,
                },
            )
            try:
                connection = (
                    GarminConnection.objects.using(using)
                    .select_for_update()
                    .get(pk=connection.pk)
                )
            except ObjectDoesNotExist as exc:
                raise ValueError("Garmin connection is not active") from exc
            expected_status = connection.status
            expected_provider_account_id = connection.provider_account_id
            connection_pk = connection.pk

            try:
                GarminOAuthState.consume_for_user(
                    user=user,
                    raw_state=state,
                    provider=GARMIN_PROVIDER,
                    using=using,
                )
            except (GarminOAuthState.DoesNotExist, ValueError) as exc:
                raise ValueError("OAuth state is invalid or expired") from exc
            connection.connection_generation += 1
            attempt_generation = connection.connection_generation
            connection.save(
                using=using,
                update_fields=["connection_generation", "updated_at"],
            )

        try:
            token_pair = exchange_code_for_tokens(code)
        except Exception as exc:
            _delete_pristine_authorization_placeholder(
                connection_pk=connection_pk,
                attempt_generation=attempt_generation,
                using=using,
            )
            raise ValueError(
                "Garmin connection state changed during authorization"
            ) from exc

        ownership_conflict = False
        with transaction.atomic(using=using):
            persisted_connection = (
                GarminConnection.objects.using(using)
                .select_for_update()
                .filter(pk=connection_pk)
                .first()
            )
            if persisted_connection is None or (
                persisted_connection.connection_generation
                != attempt_generation
                or persisted_connection.status != expected_status
                or persisted_connection.provider_account_id
                != expected_provider_account_id
            ):
                raise ValueError(
                    "Garmin connection state changed during authorization"
                )
            connection = persisted_connection

            if connection.provider != GARMIN_PROVIDER:
                connection.provider = GARMIN_PROVIDER
            account_switched = _provider_account_switches_without_history(
                connection,
                token_pair.provider_account_id,
                using=using,
            )
            connection.set_tokens(token_pair, expires_in=token_pair.expires_in)
            if account_switched:
                connection.last_sync_summary = {}
                connection.last_synced_at = None

            if (
                connection.provider_account_id
                and GarminConnection.objects.using(using)
                .filter(
                    provider=connection.provider,
                    provider_account_id=connection.provider_account_id,
                )
                .exclude(pk=connection.pk)
                .exists()
            ):
                ownership_conflict = True
            else:
                updated_rows = 0
                try:
                    with transaction.atomic(using=using):
                        updated_rows = (
                            GarminConnection.objects.using(using)
                            .filter(
                                pk=connection.pk,
                                connection_generation=attempt_generation,
                                status=expected_status,
                                provider_account_id=(
                                    expected_provider_account_id
                                ),
                            )
                            .update(
                                provider=connection.provider,
                                provider_account_id=(
                                    connection.provider_account_id
                                ),
                                provider_scopes=connection.provider_scopes,
                                access_token_encrypted=(
                                    connection.access_token_encrypted
                                ),
                                refresh_token_encrypted=(
                                    connection.refresh_token_encrypted
                                ),
                                access_token_expires_at=(
                                    connection.access_token_expires_at
                                ),
                                status=connection.status,
                                connection_generation=(
                                    connection.connection_generation
                                ),
                                authorization_placeholder=(
                                    connection.authorization_placeholder
                                ),
                                last_synced_at=connection.last_synced_at,
                                last_sync_summary=(
                                    connection.last_sync_summary
                                ),
                                updated_at=timezone.now(),
                            )
                        )
                except IntegrityError as exc:
                    if not is_provider_account_ownership_conflict(exc):
                        raise
                    ownership_conflict = True
                if not ownership_conflict and updated_rows != 1:
                    raise ValueError(
                        "Garmin connection state changed during authorization"
                    )

        if ownership_conflict:
            _delete_pristine_authorization_placeholder(
                connection_pk=connection_pk,
                attempt_generation=attempt_generation,
                using=using,
            )
            raise ValueError(GARMIN_PROVIDER_ACCOUNT_OWNERSHIP_CONFLICT)

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
                    "provider",
                    "access_token_expires_at",
                    "status",
                    "connection_generation",
                    "authorization_placeholder",
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


def _delete_pristine_authorization_placeholder(
    *,
    connection_pk: int,
    attempt_generation: int,
    using: str,
) -> None:
    """Delete a callback-created placeholder that never received credentials."""
    from django.db import transaction

    with transaction.atomic(using=using):
        placeholder = (
            GarminConnection.objects.using(using)
            .select_for_update()
            .filter(pk=connection_pk)
            .first()
        )
        if (
            placeholder is not None
            and placeholder.connection_generation == attempt_generation
            and placeholder.authorization_placeholder
            and placeholder.provider == GARMIN_PROVIDER
            and placeholder.status == GarminConnection.Status.DISCONNECTED
            and not placeholder.provider_account_id
            and not placeholder.provider_scopes
            and not placeholder.access_token_encrypted
            and not placeholder.refresh_token_encrypted
            and placeholder.access_token_expires_at is None
            and placeholder.last_synced_at is None
            and not placeholder.last_sync_summary
            and not placeholder.activities.exists()
        ):
            GarminConnection.objects.using(using).filter(
                pk=placeholder.pk,
                authorization_placeholder=True,
            ).delete()


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
            datetime.now(dt_timezone.utc) - timedelta(minutes=safe_offset)
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
