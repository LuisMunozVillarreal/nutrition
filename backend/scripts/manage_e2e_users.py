"""Create and remove isolated end-to-end test accounts from stdin input."""

# pylint: disable=wrong-import-position

import datetime
import os
import sys
from typing import cast

import django
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.exercises.models import Exercise  # noqa: E402
from apps.foods.models import Food  # noqa: E402
from apps.garmin.models import GarminConnection  # noqa: E402
from apps.users.models import User  # noqa: E402
from scripts.e2e_lifecycle import LifecyclePayload  # noqa: E402
from scripts.e2e_lifecycle import read_lifecycle_payload  # noqa: E402

_GARMIN_PLACEHOLDER_CIPHERTEXT = "invalid-e2e-placeholder"


def create_e2e_user(email: str, password: str, *, is_staff: bool) -> User:
    """Replace one E2E account with the requested privilege level.

    Args:
        email: Unique account email address.
        password: Generated password for this run.
        is_staff: Whether the account may mutate shared catalog data.

    Returns:
        The newly created isolated E2E user.
    """
    User.objects.filter(email=email).delete()
    return cast(
        User,
        User.objects.create_user(
            email=email,
            password=password,
            first_name="E2E",
            last_name="Staff" if is_staff else "Regular",
            date_of_birth=datetime.date(1990, 1, 1),
            height=180.0,
            is_staff=is_staff,
        ),
    )


def seed_accounts(payload: LifecyclePayload) -> None:
    """Create distinct regular and staff identities for one E2E run.

    Args:
        payload: Validated identities and credentials for the current run.
    """
    create_e2e_user(
        payload.regular_email,
        payload.regular_password,
        is_staff=False,
    )
    create_e2e_user(
        payload.staff_email,
        payload.staff_password,
        is_staff=True,
    )
    reset_garmin_connection(payload)


def _remove_garmin_fixture(user: User) -> None:
    """Remove one user's connection and only its provider-derived exercises."""
    connection = (
        GarminConnection.objects.select_for_update().filter(user=user).first()
    )
    if connection is None:
        return

    exercise_ids = tuple(
        connection.activities.filter(exercise_id__isnull=False).values_list(
            "exercise_id", flat=True
        )
    )
    if exercise_ids:
        Exercise.objects.filter(
            pk__in=exercise_ids,
            day__plan__user=user,
        ).delete()
    connection.activities.all().delete()
    GarminConnection.objects.filter(pk=connection.pk).delete()


def reset_garmin_connection(payload: LifecyclePayload) -> None:
    """Replace the regular user's Garmin fixture with one connected placeholder.

    Args:
        payload: Validated identity for the current E2E run.
    """
    with transaction.atomic():
        user = cast(
            User,
            User.objects.select_for_update().get(email=payload.regular_email),
        )
        _remove_garmin_fixture(user)
        GarminConnection.objects.create(
            user=user,
            status=GarminConnection.Status.ACTIVE,
            # Deliberately invalid and non-secret. Status and disconnect only
            # inspect/erase this value, so no provider configuration is needed.
            refresh_token_encrypted=_GARMIN_PLACEHOLDER_CIPHERTEXT,
        )


def cleanup_garmin_connection(payload: LifecyclePayload) -> None:
    """Idempotently remove the regular user's complete Garmin E2E fixture.

    Args:
        payload: Validated identity for the current E2E run.
    """
    with transaction.atomic():
        user = cast(
            User | None,
            User.objects.select_for_update()
            .filter(email=payload.regular_email)
            .first(),
        )
        if user is not None:
            _remove_garmin_fixture(user)


def cleanup_accounts(payload: LifecyclePayload) -> None:
    """Remove current-run shared catalog rows and both owned identities.

    Args:
        payload: Validated identities and fixture marker for the current run.
    """
    cleanup_garmin_connection(payload)
    fixture_ids = list(
        Food.objects.filter(name__endswith=payload.run_marker).values_list(
            "id", flat=True
        )
    )
    Food.objects.filter(id__in=fixture_ids).delete()
    User.objects.filter(
        email__in=[payload.regular_email, payload.staff_email]
    ).delete()


def main() -> None:
    """Run the requested account lifecycle action.

    Raises:
        SystemExit: If the requested action is unsupported.
    """
    actions = {
        "seed": seed_accounts,
        "reset-garmin": reset_garmin_connection,
        "cleanup-garmin": cleanup_garmin_connection,
        "cleanup": cleanup_accounts,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit(
            "Usage: python -m scripts.manage_e2e_users "
            "{seed|reset-garmin|cleanup-garmin|cleanup}"
        )
    payload = read_lifecycle_payload(sys.stdin)
    actions[sys.argv[1]](payload)


if __name__ == "__main__":
    main()
