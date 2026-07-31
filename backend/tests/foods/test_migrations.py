"""Regression tests for foods data migrations."""

# pylint: disable=too-many-lines

import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations import AddField, RunPython
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
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
        "apps.foods.migrations.0036_backfill_manual_consumed_perc"
    )
    operations = [
        operation
        for operation in migration.Migration.operations
        if isinstance(operation, RunPython)
    ]
    assert len(operations) == 1
    operations[0].code(apps, SimpleNamespace(connection=connection))


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


@pytest.mark.parametrize(
    ("migration_name", "nullable_fields"),
    [
        (
            "0032_cupboarditem_manual_consumed_perc",
            {("cupboarditem", "manual_consumed_perc")},
        ),
        (
            "0033_cupboarditemconsumption_num_servings",
            {("cupboarditemconsumption", "num_servings")},
        ),
        (
            "0034_cupboarditemconsumption_consumed_amount_and_more",
            {
                ("cupboarditemconsumption", "consumed_amount"),
                ("cupboarditemconsumption", "consumed_unit"),
                ("recipeingredient", "size_snapshot"),
                ("recipeingredient", "size_snapshot_unit"),
            },
        ),
    ],
)
def test_expansion_migrations_are_short_schema_only_steps(
    migration_name, nullable_fields
):
    """Expansion DDL is recorded before any restartable data migration."""
    migration = importlib.import_module(
        f"apps.foods.migrations.{migration_name}"
    )

    assert migration.Migration.atomic is True
    assert all(
        isinstance(operation, AddField)
        for operation in migration.Migration.operations
    )
    fields = {
        (operation.model_name, operation.name): operation.field
        for operation in migration.Migration.operations
    }
    assert set(fields) == nullable_fields
    assert all(field.null for field in fields.values())


@pytest.mark.parametrize(
    ("migration_name", "dependency"),
    [
        (
            "0036_backfill_manual_consumed_perc",
            "0035_relax_preview_snapshot_constraints",
        ),
        (
            "0037_backfill_consumption_num_servings",
            "0036_backfill_manual_consumed_perc",
        ),
        (
            "0038_backfill_serving_snapshots",
            "0037_backfill_consumption_num_servings",
        ),
    ],
)
def test_backfills_are_separately_recorded_non_atomic_data_steps(
    migration_name, dependency
):
    """Each O(N) backfill can commit bounded batches and resume independently."""
    migration = importlib.import_module(
        f"apps.foods.migrations.{migration_name}"
    )

    assert migration.Migration.atomic is False
    assert migration.Migration.dependencies == [("foods", dependency)]
    assert len(migration.Migration.operations) == 1
    operation = migration.Migration.operations[0]
    assert isinstance(operation, RunPython)
    assert operation.atomic is False


def test_preview_bridge_relaxes_old_non_null_columns_on_postgresql(
    monkeypatch,
):
    """Recorded preview 0032-0034 state is made rolling-writer compatible."""
    migration = importlib.import_module(
        "apps.foods.migrations.0035_relax_preview_snapshot_constraints"
    )
    monkeypatch.setattr(
        migration, "_ensure_snapshot_unit_column", lambda apps, editor: None
    )
    statements = []
    schema_editor = SimpleNamespace(
        connection=SimpleNamespace(vendor="postgresql"),
        quote_name=lambda value: f'"{value}"',
        execute=statements.append,
    )

    migration.relax_preview_snapshot_constraints(apps, schema_editor)

    assert len(statements) == 6
    assert all(" DROP NOT NULL" in statement for statement in statements)
    assert any("manual_consumed_perc" in statement for statement in statements)
    assert any("size_snapshot" in statement for statement in statements)
    assert any("size_snapshot_unit" in statement for statement in statements)


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
    ).update(manual_consumed_perc=None)

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
        consumed_perc=Decimal("35"), manual_consumed_perc=None
    )

    _run_manual_consumption_data_migration()

    item.refresh_from_db()
    assert item.manual_consumed_perc == Decimal("25")


@pytest.mark.django_db
def test_manual_consumption_migration_uses_bounded_restartable_batches(
    monkeypatch,
):
    """0036 bounds reads and writes while remaining safe to rerun."""
    migration = importlib.import_module(
        "apps.foods.migrations.0036_backfill_manual_consumed_perc"
    )
    batch_size = 10
    item_count = batch_size * 3 + 1
    expected_batches = 4
    monkeypatch.setattr(migration, "BATCH_SIZE", batch_size, raising=False)
    product = FoodProduct.objects.create(name="High-cardinality baseline")
    CupboardItem.objects.bulk_create(
        [
            CupboardItem(
                food=product,
                purchased_at=timezone.now(),
                consumed_perc=Decimal("25"),
                manual_consumed_perc=None,
            )
            for _ in range(item_count)
        ]
    )
    statements = []

    def record_statement(execute, sql, params, many, context):
        del context
        statements.append((sql, params))
        return execute(sql, params, many)

    with connection.execute_wrapper(record_statement):
        _run_manual_consumption_data_migration()

    item_table = CupboardItem._meta.db_table
    consumption_table = CupboardItemConsumption._meta.db_table
    item_selects = [
        sql
        for sql, _params in statements
        if sql.lstrip().upper().startswith("SELECT")
        and f'FROM "{item_table}"' in sql
    ]
    consumption_prefetches = [
        params
        for sql, params in statements
        if sql.lstrip().upper().startswith("SELECT")
        and f'FROM "{consumption_table}"' in sql
    ]
    item_updates = [
        sql
        for sql, _params in statements
        if sql.lstrip().upper().startswith(f'UPDATE "{item_table}"'.upper())
    ]

    assert migration.Migration.atomic is False
    assert len(item_selects) == expected_batches + 1
    assert all(
        "LIMIT 1" in sql or f"LIMIT {batch_size}" in sql
        for sql in item_selects
    )
    assert len(consumption_prefetches) == expected_batches
    assert all(
        params is not None and len(params) <= batch_size
        for params in consumption_prefetches
    )
    assert len(item_updates) == expected_batches
    assert len(statements) <= 1 + expected_batches * 5
    assert set(
        CupboardItem.objects.values_list("manual_consumed_perc", flat=True)
    ) == {Decimal("25")}

    _run_manual_consumption_data_migration()

    assert set(
        CupboardItem.objects.values_list("manual_consumed_perc", flat=True)
    ) == {Decimal("25")}


@pytest.mark.django_db
def test_manual_backfill_handles_rolling_writer_insert_and_update(monkeypatch):
    """A paused batch neither skips a late row nor overwrites a dual-write."""
    migration = importlib.import_module(
        "apps.foods.migrations.0036_backfill_manual_consumed_perc"
    )
    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    product = FoodProduct.objects.create(name="Rolling writer baseline")
    raced = CupboardItem.objects.create(
        food=product,
        purchased_at=timezone.now(),
        consumed_perc=Decimal("25"),
    )
    pending = CupboardItem.objects.create(
        food=product,
        purchased_at=timezone.now(),
        consumed_perc=Decimal("30"),
    )
    CupboardItem.objects.filter(pk__in=[raced.pk, pending.pk]).update(
        manual_consumed_perc=None
    )
    late = {}
    injected = False
    item_table = CupboardItem._meta.db_table

    def write_during_first_batch(execute, sql, params, many, context):
        del context
        nonlocal injected
        if not injected and sql.lstrip().upper().startswith(
            f'UPDATE "{item_table}"'.upper()
        ):
            injected = True
            CupboardItem.objects.filter(pk=raced.pk).update(
                manual_consumed_perc=Decimal("77")
            )
            late_item = CupboardItem.objects.create(
                food=product,
                purchased_at=timezone.now(),
                consumed_perc=Decimal("40"),
            )
            CupboardItem.objects.filter(pk=late_item.pk).update(
                manual_consumed_perc=None
            )
            late["pk"] = late_item.pk
        return execute(sql, params, many)

    with connection.execute_wrapper(write_during_first_batch):
        _run_manual_consumption_data_migration()

    assert CupboardItem.objects.get(pk=raced.pk).manual_consumed_perc == 77
    assert CupboardItem.objects.get(pk=pending.pk).manual_consumed_perc == 30
    assert CupboardItem.objects.get(pk=late["pk"]).manual_consumed_perc == 40


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
    ).update(num_servings=None)

    _run_data_migration("0037_backfill_consumption_num_servings")

    intake_link.refresh_from_db()
    legacy_link.refresh_from_db()
    assert intake_link.num_servings == Decimal("2.5")
    assert legacy_link.num_servings == Decimal("1")


@pytest.mark.django_db
def test_quantity_backfill_handles_rolling_writer_insert_and_update(
    monkeypatch,
):
    """0037 preserves a raced value and revisits a late high-key null row."""
    migration = importlib.import_module(
        "apps.foods.migrations.0037_backfill_consumption_num_servings"
    )
    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    product = FoodProduct.objects.create(name="Rolling quantities", size=400)
    serving = product.servings.get(serving_size=100, serving_unit="g")
    item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    raced = CupboardItemConsumption.objects.create(item=item, serving=serving)
    pending = CupboardItemConsumption.objects.create(
        item=item, serving=serving
    )
    CupboardItemConsumption.objects.filter(
        pk__in=[raced.pk, pending.pk]
    ).update(num_servings=None)
    table = CupboardItemConsumption._meta.db_table
    late = {}
    injected = False
    bulk_updates = []

    def write_during_first_batch(execute, sql, params, many, context):
        del context
        nonlocal injected
        is_bulk_update = (
            sql.lstrip().upper().startswith(f'UPDATE "{table}"'.upper())
            and "CASE" in sql.upper()
        )
        if is_bulk_update:
            bulk_updates.append(sql)
        if not injected and is_bulk_update:
            injected = True
            CupboardItemConsumption.objects.filter(pk=raced.pk).update(
                num_servings=Decimal("7")
            )
            late_link = CupboardItemConsumption.objects.create(
                item=item, serving=serving
            )
            CupboardItemConsumption.objects.filter(pk=late_link.pk).update(
                num_servings=None
            )
            late["pk"] = late_link.pk
        return execute(sql, params, many)

    with connection.execute_wrapper(write_during_first_batch):
        _run_data_migration("0037_backfill_consumption_num_servings")

    assert CupboardItemConsumption.objects.get(pk=raced.pk).num_servings == 7
    assert CupboardItemConsumption.objects.get(pk=pending.pk).num_servings == 1
    assert CupboardItemConsumption.objects.get(pk=late["pk"]).num_servings == 1
    assert len(bulk_updates) == 3


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
    RecipeIngredient.objects.filter(pk=ingredient.pk).update(
        size_snapshot=None, size_snapshot_unit=None
    )
    CupboardItemConsumption.objects.filter(pk=consumption.pk).update(
        consumed_amount=None, consumed_unit=None
    )

    _run_data_migration("0038_backfill_serving_snapshots")

    ingredient.refresh_from_db()
    consumption.refresh_from_db()
    assert ingredient.size_snapshot == Decimal("1000")
    assert ingredient.size_snapshot_unit == "g"
    assert consumption.consumed_amount == Decimal("112.5")
    assert consumption.consumed_unit == "g"


@pytest.mark.django_db
# pylint: disable-next=too-many-locals
def test_snapshot_migration_uses_bounded_pair_updates(monkeypatch):
    """0038 bounds reads and writes without issuing updates per row."""
    migration = importlib.import_module(
        "apps.foods.migrations.0038_backfill_serving_snapshots"
    )
    batch_size = 2
    row_count = 5
    expected_batches = 3
    monkeypatch.setattr(migration, "BATCH_SIZE", batch_size)
    product = FoodProduct.objects.create(name="Bounded snapshots", size=1000)
    serving = product.servings.get(serving_size=100, serving_unit="g")
    recipe = Recipe.objects.create(name="Bounded snapshot recipe")
    ingredients = [
        RecipeIngredient.objects.create(recipe=recipe, food=serving)
        for _ in range(row_count)
    ]
    item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    consumptions = [
        CupboardItemConsumption.objects.create(item=item, serving=serving)
        for _ in range(row_count)
    ]
    RecipeIngredient.objects.filter(
        pk__in=[ingredient.pk for ingredient in ingredients]
    ).update(size_snapshot=None, size_snapshot_unit=None)
    CupboardItemConsumption.objects.filter(
        pk__in=[consumption.pk for consumption in consumptions]
    ).update(consumed_amount=None, consumed_unit=None)
    statements = []

    def record_statement(execute, sql, params, many, context):
        del context
        statements.append((sql, params))
        return execute(sql, params, many)

    with connection.execute_wrapper(record_statement):
        _run_data_migration("0038_backfill_serving_snapshots")

    ingredient_table = RecipeIngredient._meta.db_table
    consumption_table = CupboardItemConsumption._meta.db_table
    ingredient_selects = [
        sql
        for sql, _params in statements
        if sql.lstrip().upper().startswith("SELECT")
        and f'FROM "{ingredient_table}"' in sql
    ]
    consumption_selects = [
        sql
        for sql, _params in statements
        if sql.lstrip().upper().startswith("SELECT")
        and f'FROM "{consumption_table}"' in sql
    ]
    ingredient_updates = [
        sql
        for sql, _params in statements
        if sql.lstrip()
        .upper()
        .startswith(f'UPDATE "{ingredient_table}"'.upper())
    ]
    consumption_updates = [
        sql
        for sql, _params in statements
        if sql.lstrip()
        .upper()
        .startswith(f'UPDATE "{consumption_table}"'.upper())
    ]

    assert len(ingredient_selects) == expected_batches + 1
    assert len(consumption_selects) == expected_batches + 1
    assert all(f"LIMIT {batch_size}" in sql for sql in ingredient_selects[:-1])
    assert all(
        f"LIMIT {batch_size}" in sql for sql in consumption_selects[:-1]
    )
    assert len(ingredient_updates) == expected_batches
    assert len(consumption_updates) == expected_batches
    assert all(
        "size_snapshot" in sql and "size_snapshot_unit" in sql
        for sql in ingredient_updates
    )
    assert all(
        "consumed_amount" in sql and "consumed_unit" in sql
        for sql in consumption_updates
    )


@pytest.mark.django_db
def test_snapshot_backfill_handles_rolling_writer_insert_and_update(
    monkeypatch,
):
    """0038 conditionally preserves a raced snapshot and reaches a late row."""
    migration = importlib.import_module(
        "apps.foods.migrations.0038_backfill_serving_snapshots"
    )
    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    product = FoodProduct.objects.create(name="Rolling snapshots", size=400)
    serving = product.servings.get(serving_size=100, serving_unit="g")
    item = CupboardItem.objects.create(
        food=product, purchased_at=timezone.now()
    )
    raced = CupboardItemConsumption.objects.create(item=item, serving=serving)
    pending = CupboardItemConsumption.objects.create(
        item=item, serving=serving
    )
    CupboardItemConsumption.objects.filter(
        pk__in=[raced.pk, pending.pk]
    ).update(consumed_amount=None, consumed_unit=None)
    table = CupboardItemConsumption._meta.db_table
    late = {}
    injected = False
    bulk_updates = []

    def write_during_first_batch(execute, sql, params, many, context):
        del context
        nonlocal injected
        is_bulk_update = (
            sql.lstrip().upper().startswith(f'UPDATE "{table}"'.upper())
            and "CASE" in sql.upper()
        )
        if is_bulk_update:
            bulk_updates.append(sql)
        if not injected and is_bulk_update:
            injected = True
            CupboardItemConsumption.objects.filter(pk=raced.pk).update(
                consumed_amount=Decimal("77"), consumed_unit="g"
            )
            late_link = CupboardItemConsumption.objects.create(
                item=item, serving=serving
            )
            CupboardItemConsumption.objects.filter(pk=late_link.pk).update(
                consumed_amount=None, consumed_unit=None
            )
            late["pk"] = late_link.pk
        return execute(sql, params, many)

    with connection.execute_wrapper(write_during_first_batch):
        _run_data_migration("0038_backfill_serving_snapshots")

    raced.refresh_from_db()
    pending.refresh_from_db()
    late_link = CupboardItemConsumption.objects.get(pk=late["pk"])
    assert (raced.consumed_amount, raced.consumed_unit) == (Decimal("77"), "g")
    assert (pending.consumed_amount, pending.consumed_unit) == (
        Decimal("100"),
        "g",
    )
    assert (late_link.consumed_amount, late_link.consumed_unit) == (
        Decimal("100"),
        "g",
    )
    assert len(bulk_updates) == 3


@pytest.mark.django_db
def test_ingredient_snapshot_backfill_handles_rolling_writer_insert_and_update(
    monkeypatch,
):
    """0038 fills snapshot pairs without overwriting a raced dual-write."""
    migration = importlib.import_module(
        "apps.foods.migrations.0038_backfill_serving_snapshots"
    )
    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    product = FoodProduct.objects.create(name="Rolling ingredients", size=400)
    serving = product.servings.get(serving_size=100, serving_unit="g")
    recipe = Recipe.objects.create(name="Rolling recipe")
    raced = RecipeIngredient.objects.create(recipe=recipe, food=serving)
    pending = RecipeIngredient.objects.create(recipe=recipe, food=serving)
    RecipeIngredient.objects.filter(pk__in=[raced.pk, pending.pk]).update(
        size_snapshot=None, size_snapshot_unit=None
    )
    table = RecipeIngredient._meta.db_table
    late = {}
    injected = False
    bulk_updates = []

    def write_during_first_batch(execute, sql, params, many, context):
        del context
        nonlocal injected
        is_bulk_update = (
            sql.lstrip().upper().startswith(f'UPDATE "{table}"'.upper())
            and "CASE" in sql.upper()
        )
        if is_bulk_update:
            bulk_updates.append(sql)
        if not injected and is_bulk_update:
            injected = True
            RecipeIngredient.objects.filter(pk=raced.pk).update(
                size_snapshot=Decimal("77"), size_snapshot_unit="kg"
            )
            late_ingredient = RecipeIngredient.objects.create(
                recipe=recipe, food=serving
            )
            RecipeIngredient.objects.filter(pk=late_ingredient.pk).update(
                size_snapshot=None, size_snapshot_unit=None
            )
            late["pk"] = late_ingredient.pk
        return execute(sql, params, many)

    with connection.execute_wrapper(write_during_first_batch):
        _run_data_migration("0038_backfill_serving_snapshots")

    raced.refresh_from_db()
    pending.refresh_from_db()
    late_ingredient = RecipeIngredient.objects.get(pk=late["pk"])
    assert (raced.size_snapshot, raced.size_snapshot_unit) == (
        Decimal("77"),
        "kg",
    )
    assert (pending.size_snapshot, pending.size_snapshot_unit) == (
        Decimal("100"),
        "g",
    )
    assert (
        late_ingredient.size_snapshot,
        late_ingredient.size_snapshot_unit,
    ) == (
        Decimal("100"),
        "g",
    )
    assert len(bulk_updates) == 3


@pytest.mark.django_db(transaction=True)
def test_snapshot_backfill_resumes_after_a_committed_batch_failure(
    monkeypatch,
):
    """A restarted 0038 skips its committed pair and completes remaining nulls."""
    migration = importlib.import_module(
        "apps.foods.migrations.0038_backfill_serving_snapshots"
    )
    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    product = FoodProduct.objects.create(
        name="Restartable snapshots", size=400
    )
    serving = product.servings.get(serving_size=100, serving_unit="g")
    recipe = Recipe.objects.create(name="Restartable recipe")
    ingredients = [
        RecipeIngredient.objects.create(recipe=recipe, food=serving)
        for _ in range(2)
    ]
    RecipeIngredient.objects.filter(
        pk__in=[ingredient.pk for ingredient in ingredients]
    ).update(size_snapshot=None, size_snapshot_unit=None)
    table = RecipeIngredient._meta.db_table
    update_count = 0

    def fail_second_batch(execute, sql, params, many, context):
        del context
        nonlocal update_count
        is_bulk_update = (
            sql.lstrip().upper().startswith(f'UPDATE "{table}"'.upper())
            and "CASE" in sql.upper()
        )
        if is_bulk_update:
            update_count += 1
            if update_count == 2:
                raise RuntimeError("injected snapshot batch failure")
        return execute(sql, params, many)

    with connection.execute_wrapper(fail_second_batch):
        with pytest.raises(
            RuntimeError, match="injected snapshot batch failure"
        ):
            _run_data_migration("0038_backfill_serving_snapshots")

    assert list(
        RecipeIngredient.objects.filter(
            pk__in=[ingredient.pk for ingredient in ingredients]
        )
        .order_by("pk")
        .values_list("size_snapshot", "size_snapshot_unit")
    ) == [(Decimal("100"), "g"), (None, None)]

    _run_data_migration("0038_backfill_serving_snapshots")

    assert list(
        RecipeIngredient.objects.filter(
            pk__in=[ingredient.pk for ingredient in ingredients]
        )
        .order_by("pk")
        .values_list("size_snapshot", "size_snapshot_unit")
    ) == [(Decimal("100"), "g"), (Decimal("100"), "g")]


@pytest.mark.django_db(transaction=True)
# pylint: disable-next=R0914
def test_clean_0031_to_latest_upgrades_existing_rows(
    day_factory,
):
    """A clean production-shaped 0031 database reaches the latest graph."""
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
    old_target = ("foods", "0031_cupboarditem_owner")
    new_target = (
        "foods",
        "0038_backfill_serving_snapshots",
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
        assert ingredient.size_snapshot_unit == "g"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
# pylint: disable-next=too-many-locals
def test_recorded_preview_0034_state_bridges_forward_without_rewriting_values():
    """Already-recorded preview migrations bridge to restartable backfills."""
    product = FoodProduct.objects.create(name="Recorded preview", size=400)
    serving = product.servings.get(serving_size=100, serving_unit="g")
    item = CupboardItem.objects.create(
        food=product,
        purchased_at=timezone.now(),
        consumed_perc=Decimal("40"),
    )
    consumption = CupboardItemConsumption.objects.create(
        item=item,
        serving=serving,
        num_servings=Decimal("1.5"),
    )
    recipe = Recipe.objects.create(name="Recorded preview recipe")
    ingredient = RecipeIngredient.objects.create(recipe=recipe, food=serving)
    expected = (
        item.manual_consumed_perc,
        consumption.num_servings,
        consumption.consumed_amount,
        consumption.consumed_unit,
        ingredient.size_snapshot,
    )
    old_target = (
        "foods",
        "0034_cupboarditemconsumption_consumed_amount_and_more",
    )
    latest_target = ("foods", "0038_backfill_serving_snapshots")

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([old_target])
        old_apps = executor.loader.project_state([old_target]).apps
        old_ingredient_model = old_apps.get_model("foods", "RecipeIngredient")
        snapshot_unit_field = old_ingredient_model._meta.get_field(
            "size_snapshot_unit"
        )
        with connection.schema_editor() as schema_editor:
            schema_editor.remove_field(
                old_ingredient_model, snapshot_unit_field
            )
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, old_ingredient_model._meta.db_table
                )
            }
        assert snapshot_unit_field.column not in columns

        executor = MigrationExecutor(connection)
        executor.migrate([latest_target])
        latest_apps = executor.loader.project_state([latest_target]).apps
        historical_item = latest_apps.get_model("foods", "CupboardItem")
        historical_consumption = latest_apps.get_model(
            "foods", "CupboardItemConsumption"
        )
        historical_ingredient = latest_apps.get_model(
            "foods", "RecipeIngredient"
        )

        bridged_item = historical_item.objects.get(pk=item.pk)
        bridged_consumption = historical_consumption.objects.get(
            pk=consumption.pk
        )
        bridged_ingredient = historical_ingredient.objects.get(
            pk=ingredient.pk
        )
        assert (
            bridged_item.manual_consumed_perc,
            bridged_consumption.num_servings,
            bridged_consumption.consumed_amount,
            bridged_consumption.consumed_unit,
            bridged_ingredient.size_snapshot,
        ) == expected
        assert bridged_ingredient.size_snapshot_unit == "g"
        assert (
            MigrationRecorder(connection)
            .migration_qs.filter(
                app="foods",
                name="0035_relax_preview_snapshot_constraints",
            )
            .exists()
        )
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def test_0036_treats_null_food_size_as_ambiguous():
    """A corrupt nullable historical denominator cannot block the backfill."""
    migration = importlib.import_module(
        "apps.foods.migrations.0036_backfill_manual_consumed_perc"
    )
    linked_totals = {1: Decimal("0")}
    ambiguous_items = set()
    consumption = SimpleNamespace(item_id=1)
    items = {1: SimpleNamespace(pk=1, food=SimpleNamespace(size=None))}

    # pylint: disable-next=protected-access
    migration._add_linked_consumption(
        linked_totals, ambiguous_items, consumption, items
    )

    assert linked_totals == {1: Decimal("0")}
    assert ambiguous_items == {1}


@pytest.mark.django_db(transaction=True)
# pylint: disable-next=too-many-locals
def test_0036_uses_canonical_cup_semantics_in_historical_state():
    """Historical cup links convert both ways before exact remainder rounding."""
    start_target = ("foods", "0035_relax_preview_snapshot_constraints")
    migration_target = ("foods", "0036_backfill_manual_consumed_perc")
    executor = MigrationExecutor(connection)

    try:
        executor.migrate([start_target])
        historical_apps = executor.loader.project_state([start_target]).apps
        historical_food = historical_apps.get_model("foods", "Food")
        historical_serving = historical_apps.get_model("foods", "Serving")
        historical_item = historical_apps.get_model("foods", "CupboardItem")
        historical_consumption = historical_apps.get_model(
            "foods", "CupboardItemConsumption"
        )

        cup_to_ml_food = historical_food.objects.create(
            name="Historical cup to millilitres",
            size=Decimal("500"),
            size_unit="ml",
        )
        ml_to_cup_food = historical_food.objects.create(
            name="Historical millilitres to cups",
            size=Decimal("2"),
            size_unit="c",
        )
        cup_serving = historical_serving.objects.create(
            food=cup_to_ml_food,
            serving_size=Decimal("1"),
            serving_unit="c",
        )
        ml_serving = historical_serving.objects.create(
            food=ml_to_cup_food,
            serving_size=Decimal("300"),
            serving_unit="ml",
        )
        items = [
            historical_item.objects.create(
                food=cup_to_ml_food,
                purchased_at=timezone.now(),
                consumed_perc=Decimal("60"),
                manual_consumed_perc=None,
            ),
            historical_item.objects.create(
                food=ml_to_cup_food,
                purchased_at=timezone.now(),
                consumed_perc=Decimal("80"),
                manual_consumed_perc=None,
            ),
            historical_item.objects.create(
                food=ml_to_cup_food,
                purchased_at=timezone.now(),
                consumed_perc=Decimal("60"),
                manual_consumed_perc=None,
            ),
        ]
        historical_consumption.objects.create(
            item=items[0], serving=cup_serving
        )
        for item in items[1:]:
            historical_consumption.objects.create(
                item=item, serving=ml_serving
            )

        executor = MigrationExecutor(connection)
        executor.migrate([migration_target])
        migrated_apps = executor.loader.project_state([migration_target]).apps
        migrated_item = migrated_apps.get_model("foods", "CupboardItem")

        assert list(
            migrated_item.objects.filter(pk__in=[item.pk for item in items])
            .order_by("pk")
            .values_list("manual_consumed_perc", flat=True)
        ) == [Decimal("12.68"), Decimal("16.60"), Decimal("0.00")]
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
# pylint: disable-next=too-many-locals
def test_0036_quarantines_nonpositive_sizes_without_changing_valid_rows():
    """Historical non-positive denominators use the ambiguous baseline."""
    start_target = ("foods", "0035_relax_preview_snapshot_constraints")
    migration_target = ("foods", "0036_backfill_manual_consumed_perc")
    executor = MigrationExecutor(connection)

    try:
        executor.migrate([start_target])
        historical_apps = executor.loader.project_state([start_target]).apps
        historical_food = historical_apps.get_model("foods", "Food")
        historical_serving = historical_apps.get_model("foods", "Serving")
        historical_item = historical_apps.get_model("foods", "CupboardItem")
        historical_consumption = historical_apps.get_model(
            "foods", "CupboardItemConsumption"
        )

        invalid_foods = [
            historical_food.objects.create(
                name=f"Non-positive historical food {size}", size=Decimal(size)
            )
            for size in ("0", "-1")
        ]
        valid_food = historical_food.objects.create(
            name="Valid historical food", size=Decimal("400")
        )
        invalid_servings = [
            historical_serving.objects.create(
                food=food,
                serving_size=Decimal("100"),
                serving_unit="g",
            )
            for food in invalid_foods
        ]
        valid_serving = historical_serving.objects.create(
            food=valid_food,
            serving_size=Decimal("100"),
            serving_unit="g",
        )
        invalid_items = [
            historical_item.objects.create(
                food=food,
                purchased_at=timezone.now(),
                consumed_perc=Decimal("40"),
                manual_consumed_perc=None,
            )
            for food in invalid_foods
        ]
        valid_item = historical_item.objects.create(
            food=valid_food,
            purchased_at=timezone.now(),
            consumed_perc=Decimal("40"),
            manual_consumed_perc=None,
        )
        for item, serving in zip(invalid_items, invalid_servings, strict=True):
            historical_consumption.objects.create(item=item, serving=serving)
        historical_consumption.objects.create(
            item=valid_item, serving=valid_serving
        )

        executor = MigrationExecutor(connection)
        executor.migrate([migration_target])
        migrated_apps = executor.loader.project_state([migration_target]).apps
        migrated_item = migrated_apps.get_model("foods", "CupboardItem")

        assert list(
            migrated_item.objects.filter(
                pk__in=[item.pk for item in invalid_items] + [valid_item.pk]
            )
            .order_by("pk")
            .values_list("manual_consumed_perc", flat=True)
        ) == [Decimal("0"), Decimal("0"), Decimal("15")]
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_committed_batch_failure_resumes_with_a_fresh_executor(monkeypatch):
    """A failed non-atomic operation resumes from its committed null-only work."""
    migration = importlib.import_module(
        "apps.foods.migrations.0036_backfill_manual_consumed_perc"
    )
    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    start_target = ("foods", "0035_relax_preview_snapshot_constraints")
    failed_target = ("foods", "0036_backfill_manual_consumed_perc")
    latest_target = ("foods", "0038_backfill_serving_snapshots")
    executor = MigrationExecutor(connection)
    executor.migrate([start_target])
    product = FoodProduct.objects.create(name="Restartable batches")
    items = [
        CupboardItem.objects.create(
            food=product,
            purchased_at=timezone.now(),
            consumed_perc=Decimal(value),
        )
        for value in ("20", "30")
    ]
    CupboardItem.objects.filter(pk__in=[item.pk for item in items]).update(
        manual_consumed_perc=None
    )
    item_table = CupboardItem._meta.db_table
    update_count = 0

    def fail_second_batch(execute, sql, params, many, context):
        del context
        nonlocal update_count
        if sql.lstrip().upper().startswith(f'UPDATE "{item_table}"'.upper()):
            update_count += 1
            if update_count == 2:
                raise RuntimeError("injected committed-batch failure")
        return execute(sql, params, many)

    try:
        with connection.execute_wrapper(fail_second_batch):
            with pytest.raises(
                RuntimeError, match="injected committed-batch failure"
            ):
                executor = MigrationExecutor(connection)
                executor.migrate([failed_target])

        values_after_failure = list(
            CupboardItem.objects.filter(pk__in=[item.pk for item in items])
            .order_by("pk")
            .values_list("manual_consumed_perc", flat=True)
        )
        assert values_after_failure == [Decimal("20"), None]
        assert (
            not MigrationRecorder(connection)
            .migration_qs.filter(app="foods", name=failed_target[1])
            .exists()
        )

        fresh_executor = MigrationExecutor(connection)
        fresh_executor.migrate([latest_target])

        assert list(
            CupboardItem.objects.filter(pk__in=[item.pk for item in items])
            .order_by("pk")
            .values_list("manual_consumed_perc", flat=True)
        ) == [Decimal("20"), Decimal("30")]
        assert (
            MigrationRecorder(connection)
            .migration_qs.filter(app="foods", name=failed_target[1])
            .exists()
        )
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
