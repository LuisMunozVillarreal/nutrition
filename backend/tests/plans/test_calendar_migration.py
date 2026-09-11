"""Populated historical-schema checks for calendar uniqueness constraints."""

import datetime

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

OLD_TARGET = (
    "plans",
    "0032_alter_day_carbs_g_alter_day_carbs_g_goal_and_more",
)
NEW_TARGET = (
    "plans",
    "0033_day_unique_plan_day_day_unique_plan_day_num_and_more",
)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("conflict", [None, "week", "day", "day_num"])
def test_calendar_constraints_preserve_populated_history(
    user, measurement_factory, conflict
):
    """Apply without rewriting data, or fail atomically without deleting conflicts."""
    # Keep historical setup, failure rollback and fresh-executor retry together.
    # pylint: disable=too-many-locals,too-many-statements
    measurement = measurement_factory(user=user)
    duplicate = None
    try:
        executor = MigrationExecutor(connection)
        targets = [OLD_TARGET] + [
            node
            for node in executor.loader.graph.leaf_nodes()
            if node[0] != "plans"
        ]
        executor.migrate(targets)
        historical = executor.loader.project_state(targets).apps
        week_model = historical.get_model("plans", "WeekPlan")
        day_model = historical.get_model("plans", "Day")
        intake_model = historical.get_model("plans", "Intake")
        exercise_model = historical.get_model("exercises", "Exercise")
        steps_model = historical.get_model("exercises", "DaySteps")
        week = week_model.objects.create(
            user_id=user.pk,
            measurement_id=measurement.pk,
            start_date=datetime.date(2023, 1, 11),
            protein_g_kg="2.1",
            fat_perc="23.0",
            deficit=123,
        )
        goals = {
            "protein_g_goal": "100.00",
            "fat_g_goal": "50.00",
            "carbs_g_goal": "200.00",
            "protein_g_intake_perc": "0.00",
            "fat_g_intake_perc": "0.00",
            "carbs_g_intake_perc": "0.00",
            "energy_kcal_intake_perc": "0.00",
        }
        day = day_model.objects.create(
            **goals,
            plan=week,
            day=week.start_date,
            day_num=1,
            tracked=False,
            deficit=111,
            energy_kcal_goal="1234.56",
        )
        second = day_model.objects.create(
            **goals,
            energy_kcal_goal="1500.00",
            plan=week,
            day=week.start_date + datetime.timedelta(days=1),
            day_num=2,
        )
        intake_model.objects.create(
            day=day, meal="lunch", meal_order=1, energy_kcal="321.45"
        )
        exercise_model.objects.create(day=day, type="walk", kcals=101)
        steps_model.objects.create(day=day, steps=123)
        if conflict == "week":
            values = week_model.objects.filter(pk=week.pk).values().get()
            values.pop("id")
            duplicate = week_model.objects.create(**values)
        elif conflict is not None:
            values = day_model.objects.filter(pk=day.pk).values().get()
            values.pop("id")
            values["day_num" if conflict == "day" else "day"] = (
                3
                if conflict == "day"
                else week.start_date + datetime.timedelta(days=2)
            )
            duplicate = day_model.objects.create(**values)
        models = (
            week_model,
            day_model,
            intake_model,
            exercise_model,
            steps_model,
        )
        before = [
            list(model.objects.order_by("pk").values()) for model in models
        ]
        executor = MigrationExecutor(connection)
        if conflict is None:
            executor.migrate([NEW_TARGET])
            with pytest.raises(IntegrityError), transaction.atomic():
                day_model.objects.filter(pk=second.pk).update(day=day.day)
        else:
            with pytest.raises(IntegrityError):
                executor.migrate([NEW_TARGET])
            assert (
                not MigrationRecorder(connection)
                .migration_qs.filter(app=NEW_TARGET[0], name=NEW_TARGET[1])
                .exists()
            )
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(
                    cursor, day_model._meta.db_table
                )
            assert "unique_plan_day" not in constraints
            assert "unique_plan_day_num" not in constraints
        assert [
            list(model.objects.order_by("pk").values()) for model in models
        ] == before
        if duplicate is not None:
            # Test-only cleanup lets a fresh executor prove a corrected retry.
            duplicate.delete()
            duplicate = None
        MigrationExecutor(connection).migrate([NEW_TARGET])
        assert (
            MigrationRecorder(connection)
            .migration_qs.filter(app=NEW_TARGET[0], name=NEW_TARGET[1])
            .exists()
        )
    finally:
        if duplicate is not None:
            duplicate.delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
