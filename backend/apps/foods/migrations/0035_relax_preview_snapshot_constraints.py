"""Relax constraints left by the already-applied branch-preview graph."""

from django.db import migrations

NULLABLE_COLUMNS = {
    "CupboardItem": ("manual_consumed_perc",),
    "CupboardItemConsumption": (
        "num_servings",
        "consumed_amount",
        "consumed_unit",
    ),
    "RecipeIngredient": ("size_snapshot", "size_snapshot_unit"),
}


def _physical_column_names(connection, table):
    """Return the physical columns recorded for a database table."""
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, table
            )
        }


def _ensure_snapshot_unit_column(apps, schema_editor):
    """Add the unit column omitted by the previously recorded preview 0034."""
    model = apps.get_model("foods", "RecipeIngredient")
    field = model._meta.get_field("size_snapshot_unit")
    columns = _physical_column_names(
        schema_editor.connection, model._meta.db_table
    )
    if field.column not in columns:
        schema_editor.add_field(model, field)


def relax_preview_snapshot_constraints(apps, schema_editor):
    """Idempotently bridge old physical preview schemas to the clean graph."""
    _ensure_snapshot_unit_column(apps, schema_editor)
    if schema_editor.connection.vendor != "postgresql":
        return

    quote = schema_editor.quote_name
    for model_name, columns in NULLABLE_COLUMNS.items():
        model = apps.get_model("foods", model_name)
        table = quote(model._meta.db_table)
        for column in columns:
            schema_editor.execute(
                f"ALTER TABLE {table} ALTER COLUMN {quote(column)} DROP NOT NULL"
            )


class Migration(migrations.Migration):
    """Bridge the old preview schema to the new expansion protocol."""

    dependencies = [
        (
            "foods",
            "0034_cupboarditemconsumption_consumed_amount_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            relax_preview_snapshot_constraints,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
