"""Create and remove isolated end-to-end test accounts from environment input."""

import datetime
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.users.models import User  # noqa: E402


def required_environment(name: str) -> str:
    """Return a required non-empty environment value."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def create_e2e_user(email: str, password: str, *, is_staff: bool) -> None:
    """Replace one E2E account with the requested privilege level."""
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


def seed_accounts() -> None:
    """Create distinct regular and staff identities for one E2E run."""
    regular_email = required_environment("E2E_REGULAR_EMAIL")
    staff_email = required_environment("E2E_STAFF_EMAIL")
    if regular_email == staff_email:
        raise RuntimeError("E2E regular and staff accounts must be distinct")

    create_e2e_user(
        regular_email,
        required_environment("E2E_REGULAR_PASSWORD"),
        is_staff=False,
    )
    create_e2e_user(
        staff_email, required_environment("E2E_STAFF_PASSWORD"), is_staff=True
    )


def cleanup_accounts() -> None:
    """Remove both identities, including the privileged account."""
    emails = [
        required_environment("E2E_REGULAR_EMAIL"),
        required_environment("E2E_STAFF_EMAIL"),
    ]
    User.objects.filter(email__in=emails).delete()


def main() -> None:
    """Run the requested account lifecycle action."""
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "cleanup"}:
        raise SystemExit(
            "Usage: python -m scripts.manage_e2e_users {seed|cleanup}"
        )
    if sys.argv[1] == "seed":
        seed_accounts()
    else:
        cleanup_accounts()


if __name__ == "__main__":
    main()
