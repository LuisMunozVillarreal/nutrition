"""Regression tests for foods data migrations."""

import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations import RunPython
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)

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


def _run_manual_consumption_data_migration() -> None:
    """Run the manual cupboard baseline initialization operation."""
    migration = importlib.import_module(
        "apps.foods.migrations.0032_cupboarditem_manual_consumed_perc"
    )
    operations = [
        operation
        for operation in migration.Migration.operations
        if isinstance(operation, RunPython)
    ]
    assert len(operations) == 1
    operations[0].code(apps, None)


def _run_data_migration(migration_name: str) -> None:
    """Run the sole forward data operation registered by a migration."""
    migration = importlib.import_module(
        f"apps.foods.migrations.{migration_name}"
    )
    operations = [
        operation
        for operation in migration.Migration.operations
        if isinstance(operation, RunPython)
    ]
    assert len(operations) == 1
    operations[0].code(apps, SimpleNamespace(connection=connection))


@pytest.mark.django_db
class TestCupboardOwnerMigration:
    """Test quarantine of inventory whose historical owner is unknowable."""

    def test_keeps_legacy_inventory_unowned_with_a_sole_user(self):
        """Even one current account is not evidence of historical ownership."""
        _create_user("sole@test.com")
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner is None

    def test_keeps_legacy_inventory_unowned_with_multiple_users(self):
        """Privilege and account age must not invent historical attribution."""
        _create_user("regular@test.com")
        _create_user("staff@test.com", is_staff=True)
        _create_user("superuser@test.com", is_superuser=True)
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner is None

    def test_keeps_legacy_inventory_unowned_when_no_user_exists(self):
        """Empty-user installations migrate successfully without inventing an owner."""
        item = _create_legacy_item()

        _run_owner_data_migration()

        item.refresh_from_db()
        assert item.owner is None


@pytest.mark.django_db
def test_manual_consumption_migration_subtracts_unit_safe_linked_totals():
    """Legacy baselines are the non-negative remainder after linked usage."""
    product = FoodProduct.objects.create(name="Legacy baseline", size=400)
    manual_item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now(), consumed_perc=25
    )
    linked_item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    overlinked_item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    serving = product.servings.get(serving_size=100, serving_unit="g")
    CupboardItemConsumption.objects.create(item=linked_item, serving=serving)
    CupboardItemConsumption.objects.create(
        item=overlinked_item, serving=serving
    )
    CupboardItem.objects.filter(pk=linked_item.pk).update(consumed_perc=40)
    CupboardItem.objects.filter(pk=overlinked_item.pk).update(consumed_perc=20)
    CupboardItem.objects.filter(
        pk__in=[manual_item.pk, linked_item.pk, overlinked_item.pk]
    ).update(manual_consumed_perc=0)

    _run_manual_consumption_data_migration()

    manual_item.refresh_from_db()
    linked_item.refresh_from_db()
    overlinked_item.refresh_from_db()
    assert manual_item.manual_consumed_perc == 25
    assert linked_item.manual_consumed_perc == Decimal("15")
    assert overlinked_item.manual_consumed_perc == 0


@pytest.mark.django_db
def test_manual_consumption_migration_handles_compatible_volume_units():
    """Historical liquid links are converted within their volume dimension."""
    product = FoodProduct.objects.create(
        name="Legacy liquid",
        nutritional_info_size=100,
        nutritional_info_unit="ml",
        size=1,
        size_unit="l",
    )
    item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    serving = product.servings.get(serving_size=100, serving_unit="ml")
    CupboardItemConsumption.objects.create(item=item, serving=serving)
    CupboardItem.objects.filter(pk=item.pk).update(
        consumed_perc=Decimal("35"), manual_consumed_perc=0
    )

    _run_manual_consumption_data_migration()

    item.refresh_from_db()
    assert item.manual_consumed_perc == Decimal("25")


@pytest.mark.django_db
def test_consumption_quantity_migration_backfills_intakes_and_legacy_links(
    day_factory,
):
    """0033 snapshots intake quantities and conservatively defaults old links."""
    product = FoodProduct.objects.create(name="Legacy quantity", size=400)
    serving = product.servings.get(serving_size=100, serving_unit="g")
    day = day_factory()
    item = CupboardItem.objects.create(
        owner=day.plan.user,
        food=product,
        purchased_at=timezone.now(),
    )
    intake = day.intakes.create(
        food=serving,
        num_servings=Decimal("2.5"),
        meal="breakfast",
    )
    intake_link = intake.cupboard_item_consumption
    legacy_link = CupboardItemConsumption.objects.create(
        item=item, serving=serving
    )
    CupboardItemConsumption.objects.filter(
        pk__in=[intake_link.pk, legacy_link.pk]
    ).update(num_servings=0)

    _run_data_migration("0033_cupboarditemconsumption_num_servings")

    intake_link.refresh_from_db()
    legacy_link.refresh_from_db()
    assert intake_link.num_servings == Decimal("2.5")
    assert legacy_link.num_servings == Decimal("1")


@pytest.mark.django_db
def test_snapshot_migration_backfills_recipe_and_consumption_amounts():
    """0034 derives stable snapshots solely from historical persisted fields."""
    product = FoodProduct.objects.create(
        name="Legacy snapshots", size=400, num_servings=4
    )
    container = product.servings.get(serving_unit="container")
    direct = Serving.objects.create(
        food=product, serving_size=Decimal("75"), serving_unit="g"
    )
    recipe = Recipe.objects.create(name="Legacy recipe", num_servings=2)
    ingredient = RecipeIngredient.objects.create(
        recipe=recipe,
        food=container,
        num_servings=Decimal("2.5"),
    )
    item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    consumption = CupboardItemConsumption.objects.create(
        item=item, serving=direct, num_servings=Decimal("1.5")
    )
    RecipeIngredient.objects.filter(pk=ingredient.pk).update(size_snapshot=0)
    CupboardItemConsumption.objects.filter(pk=consumption.pk).update(
        consumed_amount=0, consumed_unit=""
    )

    _run_data_migration(
        "0034_cupboarditemconsumption_consumed_amount_and_more"
    )

    ingredient.refresh_from_db()
    consumption.refresh_from_db()
    assert ingredient.size_snapshot == Decimal("1000")
    assert consumption.consumed_amount == Decimal("112.5")
    assert consumption.consumed_unit == "g"


@pytest.mark.django_db(transaction=True)
# pylint: disable-next=R0914
def test_snapshot_migrations_upgrade_existing_rows(
    day_factory,
):
    """0033 and 0034 backfill real rows while advancing historical state."""
    product = FoodProduct.objects.create(
        name="Historical upgrade", size=400, num_servings=4
    )
    direct = product.servings.get(serving_size=100, serving_unit="g")
    container = product.servings.get(serving_unit="container")
    day = day_factory()
    item = CupboardItem.objects.create(
        owner=day.plan.user,
        food=product,
        purchased_at=timezone.now(),
    )
    intake = day.intakes.create(
        food=direct,
        num_servings=Decimal("2.5"),
        meal="breakfast",
    )
    intake_link_id = intake.cupboard_item_consumption.pk
    legacy_link_id = CupboardItemConsumption.objects.create(
        item=item, serving=direct
    ).pk
    recipe = Recipe.objects.create(name="Historical recipe", num_servings=2)
    ingredient_id = RecipeIngredient.objects.create(
        recipe=recipe,
        food=container,
        num_servings=Decimal("2.5"),
    ).pk
    old_target = ("foods", "0032_cupboarditem_manual_consumed_perc")
    new_target = (
        "foods",
        "0034_cupboarditemconsumption_consumed_amount_and_more",
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([old_target])
        executor = MigrationExecutor(connection)
        executor.migrate([new_target])
        historical_apps = executor.loader.project_state([new_target]).apps
        historical_consumption = historical_apps.get_model(
            "foods", "CupboardItemConsumption"
        )
        historical_ingredient = historical_apps.get_model(
            "foods", "RecipeIngredient"
        )

        intake_link = historical_consumption.objects.get(pk=intake_link_id)
        legacy_link = historical_consumption.objects.get(pk=legacy_link_id)
        ingredient = historical_ingredient.objects.get(pk=ingredient_id)
        assert intake_link.num_servings == Decimal("2.5")
        assert intake_link.consumed_amount == Decimal("250")
        assert intake_link.consumed_unit == "g"
        assert legacy_link.num_servings == Decimal("1")
        assert legacy_link.consumed_amount == Decimal("100")
        assert legacy_link.consumed_unit == "g"
        assert ingredient.size_snapshot == Decimal("1000")
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
