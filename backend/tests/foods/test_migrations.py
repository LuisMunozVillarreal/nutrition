"""Regression tests for foods data migrations."""

import datetime
import importlib

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.migrations import RunPython
from django.utils import timezone

from apps.foods.models import CupboardItem, FoodProduct

User = get_user_model()


def _create_user(
    email: str, *, is_staff: bool = False, is_superuser: bool = False
):
    """Create a user suitable for migration ownership tests."""
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


def _create_legacy_item() -> CupboardItem:
    """Create the shape left by installations predating cupboard ownership."""
    product = FoodProduct.objects.create(name="Legacy", num_servings=1)
    return CupboardItem.objects.create(
        owner=None,
        food=product,
        purchased_at=timezone.now(),
    )


def _run_owner_data_migration() -> None:
    """Run the registered owner reconciliation operation."""
    migration = importlib.import_module(
        "apps.foods.migrations.0031_cupboarditem_owner"
    )
    operations = [
        operation
        for operation in migration.Migration.operations
        if isinstance(operation, RunPython)
    ]
    assert len(operations) == 1
    operations[0].code(apps, None)


@pytest.mark.django_db
class TestCupboardOwnerMigration:
    """Test deterministic reconciliation of legacy cupboard inventory."""

    def test_assigns_legacy_inventory_to_the_sole_user(self):
        """A sole account retains access to all pre-ownership inventory."""
        user = _create_user("sole@test.com")
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner == user

    def test_prefers_the_earliest_privileged_account(self):
        """Multiple-user installs assign inventory to earliest privileged user."""
        regular = _create_user("regular@test.com")
        later_staff = _create_user("later-staff@test.com", is_staff=True)
        earlier_staff = _create_user("earlier-staff@test.com", is_staff=True)
        base = timezone.now() - datetime.timedelta(days=3)
        User.objects.filter(pk=regular.pk).update(date_joined=base)
        User.objects.filter(pk=earlier_staff.pk).update(
            date_joined=base + datetime.timedelta(days=1)
        )
        User.objects.filter(pk=later_staff.pk).update(
            date_joined=base + datetime.timedelta(days=2)
        )
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner == earlier_staff

    def test_uses_the_earliest_account_when_none_are_privileged(self):
        """Multiple regular accounts fall back to the earliest account."""
        later = _create_user("later@test.com")
        earlier = _create_user("earlier@test.com")
        base = timezone.now() - datetime.timedelta(days=2)
        User.objects.filter(pk=earlier.pk).update(date_joined=base)
        User.objects.filter(pk=later.pk).update(
            date_joined=base + datetime.timedelta(days=1)
        )
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner == earlier

    def test_keeps_legacy_inventory_unowned_when_no_user_exists(self):
        """Empty-user installations migrate successfully without inventing an owner."""
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner is None
