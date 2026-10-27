"""PostgreSQL lock compatibility for calendar cascade tombstones."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from queue import Queue

import pytest
from django.db import connection, connections, transaction
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.foods.models import CupboardItem, CupboardItemConsumption, Serving
from apps.health_sync.models import ActivityImport
from apps.plans.locks import lock_plan_owner
from apps.plans.models import Day, Intake
from apps.users.models import User

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="PostgreSQL row locks required",
    ),
]


def _connection_pid():
    """Bound worker SQL and identify its independent PostgreSQL connection."""
    with connection.cursor() as cursor:
        cursor.execute("SET lock_timeout = '8s'")
        cursor.execute("SET statement_timeout = '12s'")
        cursor.execute("SELECT pg_backend_pid()")
        return cursor.fetchone()[0]


def _wait_for_blocker(waiter_pid, blocker_pid):
    """Wait for a database-confirmed dependency rather than assuming timing."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_blocking_pids(%s)", [waiter_pid])
            if blocker_pid in cursor.fetchone()[0]:
                return
        time.sleep(0.01)
    pytest.fail("The competing writer never waited on the expected connection")


@pytest.mark.parametrize("parent", ["day", "weekplan", "measurement"])
@pytest.mark.parametrize("bulk", [False, True])
def test_calendar_delete_allows_recipe_owner_fk_at_commit(
    imported_activity,
    food_product_factory,
    cupboard_item_factory,
    recipe_factory,
    recipe_ingredient_factory,
    intake_factory,
    parent,
    bulk,
):
    """A cook holding stock can commit while a calendar cascade waits for it."""
    # The checkpoints force stock -> deferred owner FK against owner -> stock.
    # pylint: disable=too-many-locals,too-many-statements
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    exercise, _token, _record = imported_activity
    day = exercise.day
    owner = day.plan.user
    root = {
        "day": day,
        "weekplan": day.plan,
        "measurement": day.plan.measurement,
    }[parent]
    product = food_product_factory(size=100, size_unit="g", num_servings=10)
    serving = Serving.objects.create(
        food=product, serving_size=10, serving_unit="g"
    )
    stock = cupboard_item_factory(
        owner=owner, food=product, consumed_perc=Decimal("5")
    )
    intake = intake_factory(day=day, food=serving, num_servings=1)
    stock.refresh_from_db()
    assert stock.consumed_perc == Decimal("15")
    recipe = recipe_factory()
    recipe_ingredient_factory(recipe=recipe, food=serving, num_servings=1)
    imported = ActivityImport.objects.get(exercise=exercise)
    interval = (imported.start_time, imported.end_time)
    stock_locked = threading.Event()
    owner_locked = threading.Event()
    release_cook = threading.Event()
    cook_pids = Queue()
    delete_pids = Queue()

    def cooking_checkpoint(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if (
            'FROM "foods_cupboarditem"' in sql
            and "FOR UPDATE" in sql
            and not stock_locked.is_set()
        ):
            stock_locked.set()
            assert release_cook.wait(timeout=10)
        return result

    def deletion_checkpoint(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if 'FROM "users_user"' in sql and "FOR " in sql:
            owner_locked.set()
        return result

    def cook():
        try:
            cook_pids.put(_connection_pid())
            with connection.execute_wrapper(cooking_checkpoint):
                return CupboardItem.objects.create(
                    owner_id=owner.pk,
                    food_id=recipe.pk,
                    purchased_at=timezone.now(),
                ).pk
        finally:
            connections.close_all()

    def delete():
        try:
            delete_pids.put(_connection_pid())
            with connection.execute_wrapper(deletion_checkpoint):
                if bulk:
                    type(root).objects.filter(pk=root.pk).delete()
                else:
                    type(root).objects.get(pk=root.pk).delete()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        cooking = pool.submit(cook)
        try:
            assert stock_locked.wait(timeout=10)
            deleting = pool.submit(delete)
            cook_pid = cook_pids.get(timeout=10)
            delete_pid = delete_pids.get(timeout=10)
            assert cook_pid != delete_pid
            assert owner_locked.wait(timeout=10)
            _wait_for_blocker(delete_pid, cook_pid)
        finally:
            release_cook.set()
        cooked_id = cooking.result(timeout=20)
        deleting.result(timeout=20)

    assert CupboardItem.objects.filter(pk=cooked_id, owner=owner).exists()
    assert not Day.objects.filter(pk=day.pk).exists()
    assert not Intake.objects.filter(pk=intake.pk).exists()
    assert not Exercise.objects.filter(pk=exercise.pk).exists()
    stock.refresh_from_db()
    assert stock.manual_consumed_perc == Decimal("5")
    assert stock.consumed_perc == Decimal("15")
    assert CupboardItemConsumption.objects.filter(item=stock).count() == 1
    imported.refresh_from_db()
    assert not imported.is_active
    assert imported.exercise_id is None
    assert (imported.start_time, imported.end_time) == interval


@pytest.mark.parametrize("delete_owner", [False, True])
def test_owner_lock_still_blocks_writers_and_user_deletion(
    user_factory, delete_owner
):
    """FK-compatible owner locks remain exclusive to writers and user DELETE."""
    user = user_factory()
    owner_locked = threading.Event()
    release_owner = threading.Event()
    holder_pids = Queue()
    contender_pids = Queue()

    def hold_owner():
        try:
            holder_pids.put(_connection_pid())
            with transaction.atomic():
                lock_plan_owner(using="default", user_id=user.pk)
                owner_locked.set()
                assert release_owner.wait(timeout=10)
                assert User.objects.filter(pk=user.pk).exists()
        finally:
            connections.close_all()

    def compete():
        try:
            contender_pids.put(_connection_pid())
            with transaction.atomic():
                if delete_owner:
                    User.objects.get(pk=user.pk).delete()
                else:
                    lock_plan_owner(using="default", user_id=user.pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        holder = pool.submit(hold_owner)
        try:
            assert owner_locked.wait(timeout=10)
            contender = pool.submit(compete)
            holder_pid = holder_pids.get(timeout=10)
            contender_pid = contender_pids.get(timeout=10)
            assert holder_pid != contender_pid
            _wait_for_blocker(contender_pid, holder_pid)
            assert not contender.done()
        finally:
            release_owner.set()
        holder.result(timeout=20)
        contender.result(timeout=20)
    assert User.objects.filter(pk=user.pk).exists() is not delete_owner
