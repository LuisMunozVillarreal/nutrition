"""Create and remove isolated end-to-end test accounts from stdin input."""

# pylint: disable=wrong-import-position

import datetime
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.foods.models import Food  # noqa: E402
from apps.users.models import User  # noqa: E402
from scripts.e2e_lifecycle import LifecyclePayload  # noqa: E402
from scripts.e2e_lifecycle import read_lifecycle_payload  # noqa: E402


def create_e2e_user(email: str, password: str, *, is_staff: bool) -> None:
    """Replace one E2E account with the requested privilege level.

    Args:
        email: Unique account email address.
        password: Generated password for this run.
        is_staff: Whether the account may mutate shared catalog data.
    """
    User.objects.filter(email=email).delete()
    User.objects.create_user(
        email=email,
        password=password,
        first_name="E2E",
        last_name="Staff" if is_staff else "Regular",
        date_of_birth=datetime.date(1990, 1, 1),
        height=180.0,
        is_staff=is_staff,
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


def cleanup_accounts(payload: LifecyclePayload) -> None:
    """Remove current-run shared catalog rows and both owned identities.

    Args:
        payload: Validated identities and fixture marker for the current run.
    """
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
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "cleanup"}:
        raise SystemExit(
            "Usage: python -m scripts.manage_e2e_users {seed|cleanup}"
        )
    payload = read_lifecycle_payload(sys.stdin)
    if sys.argv[1] == "seed":
        seed_accounts(payload)
    else:
        cleanup_accounts(payload)


if __name__ == "__main__":
    main()
