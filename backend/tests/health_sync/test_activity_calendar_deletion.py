"""Calendar deletions permanently override imported activities."""

from types import SimpleNamespace

import pytest
from django.db.models.query import QuerySet
from django.db.models.signals import post_delete

from apps.exercises.models import Exercise
from apps.health_sync.models import ActivityImport
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from apps.users.models import User
from config.schema import schema
from tests.health_sync.test_activity_admin import (
    _inline_payload,
    _replay,
)


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["day", "weekplan", "measurement"])
@pytest.mark.parametrize("bulk", [False, True])
def test_calendar_admin_delete_keeps_tombstone(
    logged_in_admin_client,
    imported_activity,
    client,
    day_factory,
    parent,
    bulk,
):
    """Actual admin single/bulk cascades cannot be undone by Garmin replay."""
    exercise, token, record = imported_activity
    day = exercise.day
    owner = day.plan.user
    root = {
        "day": day,
        "weekplan": day.plan,
        "measurement": day.plan.measurement,
    }[parent]
    app = "measurements" if parent == "measurement" else "plans"
    if bulk:
        url = f"/admin/{app}/{parent}/"
        data = {
            "action": "delete_selected",
            "post": "yes",
            "_selected_action": [root.pk],
        }
    else:
        url = f"/admin/{app}/{parent}/{root.pk}/delete/"
        data = {"post": "yes"}
    before = ActivityImport.objects.get()
    response = logged_in_admin_client.post(url, data)
    assert response.status_code == 302
    imported = ActivityImport.objects.get()
    assert not imported.is_active
    assert imported.exercise_id is None
    assert (imported.start_time, imported.end_time) == (
        before.start_time,
        before.end_time,
    )
    day_factory(
        day=day.day,
        **({"plan": day.plan} if parent == "day" else {"plan__user": owner}),
    )
    assert _replay(client, token, record)["unchanged"] == 1
    assert not Exercise.objects.filter(day__plan__user=owner).exists()


@pytest.mark.django_db
def test_nested_day_delete_keeps_tombstone(
    logged_in_admin_client, imported_activity, client, day_factory
):
    """Deleting the day inline in a week form is also a manual override."""
    exercise, token, record = imported_activity
    day = exercise.day
    url = f"/admin/plans/weekplan/{day.plan_id}/change/"
    response = logged_in_admin_client.get(url)
    data, _forms = _inline_payload(response)
    formset = response.context["inline_admin_formsets"][0].formset
    form = next(form for form in formset.forms if form.instance.pk == day.pk)
    data[form.add_prefix("DELETE")] = "on"
    response = logged_in_admin_client.post(url, data)
    assert response.status_code == 302, response.context["errors"]
    assert not Day.objects.filter(pk=day.pk).exists()
    assert not ActivityImport.objects.get().is_active
    day_factory(plan=day.plan, day=day.day)
    assert _replay(client, token, record)["unchanged"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["day", "weekplan", "measurement"])
@pytest.mark.parametrize("bulk", [False, True])
def test_calendar_delete_is_atomic_and_owner_first(
    imported_activity, parent, bulk, monkeypatch, intake_factory
):
    """Lock owners before aggregates and roll tombstones back with cascades."""
    exercise, _token, _record = imported_activity
    intake_factory(day=exercise.day)
    root = {
        "day": exercise.day,
        "weekplan": exercise.day.plan,
        "measurement": exercise.day.plan.measurement,
    }[parent]
    original_fetch = QuerySet._fetch_all
    owners = set()

    def fetch(queryset):
        result = original_fetch(queryset)
        if queryset.query.select_for_update:
            if queryset.model is User:
                owners.update(obj.pk for obj in queryset._result_cache)
            elif queryset.model in (Day, WeekPlan, Measurement):
                assert exercise.day.plan.user_id in owners
        return result

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    before = list(ActivityImport.objects.values())

    def fail(sender, instance, **kwargs):
        assert not ActivityImport.objects.get().is_active
        raise RuntimeError("calendar rollback")

    post_delete.connect(fail, sender=Exercise)
    try:
        with pytest.raises(RuntimeError, match="calendar rollback"):
            if bulk:
                type(root).objects.filter(pk=root.pk).delete()
            else:
                root.delete()
    finally:
        post_delete.disconnect(fail, sender=Exercise)
    assert Exercise.objects.filter(pk=exercise.pk).exists()
    assert list(ActivityImport.objects.values()) == before


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["weekplan", "measurement"])
def test_user_calendar_deletion_mutation_keeps_tombstone(
    imported_activity, client, day_factory, parent
):
    """Both user-facing calendar cascade mutations preserve the override."""
    exercise, token, record = imported_activity
    day = exercise.day
    user = day.plan.user
    root = day.plan if parent == "weekplan" else day.plan.measurement
    if parent == "measurement":
        root.user = user
        root.save(update_fields=["user"])
    mutation = (
        "deleteWeekPlan" if parent == "weekplan" else "deleteMeasurement"
    )
    result = schema.execute_sync(
        f"mutation Delete($id: ID!) {{ {mutation}(id: $id) }}",
        variable_values={"id": str(root.pk)},
        context_value=SimpleNamespace(request=SimpleNamespace(user=user)),
    )
    assert result.errors is None
    assert result.data[mutation] is True
    assert not ActivityImport.objects.get().is_active
    day_factory(plan__user=user, day=day.day)
    assert _replay(client, token, record)["unchanged"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["day", "weekplan", "measurement"])
def test_bulk_calendar_delete_locks_complete_owner_set(
    logged_in_admin_client, imported_activity, day_factory, parent, monkeypatch
):
    """Admin selections lock all owners before any calendar or import write."""
    exercise, _token, _record = imported_activity
    other_day = day_factory()
    days = [exercise.day, other_day]
    roots = [
        {
            "day": day,
            "weekplan": day.plan,
            "measurement": day.plan.measurement,
        }[parent]
        for day in days
    ]
    expected = sorted(
        {day.plan.user_id for day in days}
        | (
            {root.user_id for root in roots}
            if parent == "measurement"
            else set()
        )
    )
    owners = []
    original_fetch = QuerySet._fetch_all

    def fetch(queryset):
        fresh = queryset._result_cache is None
        result = original_fetch(queryset)
        if fresh and queryset.query.select_for_update:
            if queryset.model is User:
                owners.extend(obj.pk for obj in queryset._result_cache)
            elif queryset.model in (Day, WeekPlan, Measurement):
                assert owners[: len(expected)] == expected
        return result

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    app = "measurements" if parent == "measurement" else "plans"
    response = logged_in_admin_client.post(
        f"/admin/{app}/{parent}/",
        {
            "action": "delete_selected",
            "post": "yes",
            "_selected_action": [root.pk for root in reversed(roots)],
        },
    )
    assert response.status_code == 302
    assert owners == expected
    assert not ActivityImport.objects.get().is_active
