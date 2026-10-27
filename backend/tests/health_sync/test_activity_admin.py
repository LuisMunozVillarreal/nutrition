"""Garmin manual overrides through real Django admin writes."""

import datetime

import pytest
from django import forms
from django.db.models.query import QuerySet
from django.db.models.signals import post_delete, post_save
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.health_sync.models import ActivityImport
from apps.plans.models import Day, WeekPlan
from apps.users.models import User
from tests.health_sync.test_activity_api import _upload


@pytest.fixture
def exercise_writes(imported_activity):
    """Record real exercise signals after initial import setup."""
    writes = []

    def record_write(sender, instance, **kwargs):
        writes.append(instance.pk)

    post_save.connect(record_write, sender=Exercise)
    post_delete.connect(record_write, sender=Exercise)
    yield writes
    post_save.disconnect(record_write, sender=Exercise)
    post_delete.disconnect(record_write, sender=Exercise)


def _replay(client, token, record):
    assert _upload(client, token, record).json()["summary"]["unchanged"] == 1
    newer = {
        **record,
        "active_kcals": 400,
        "source_modified_at": (
            timezone.now() + datetime.timedelta(minutes=5)
        ).isoformat(),
    }
    return _upload(client, token, newer).json()["summary"]


def _exercise_data(exercise, **changes):
    data = {
        "day": exercise.day_id,
        "time": exercise.time.isoformat(),
        "type": exercise.type,
        "kcals": 999,
        "duration": str(exercise.duration),
        "distance": exercise.distance,
        "_save": "Save",
    }
    data.update(changes)
    return data


@pytest.mark.django_db
def test_admin_edit_permanently_overrides_import(
    logged_in_admin_client, imported_activity, client, exercise_writes
):
    """A real admin POST must survive newer Garmin corrections."""
    exercise, token, record = imported_activity
    response = logged_in_admin_client.post(
        f"/admin/exercises/exercise/{exercise.pk}/change/",
        _exercise_data(exercise),
    )
    assert response.status_code == 302
    assert _replay(client, token, record)["unchanged"] == 1
    exercise.refresh_from_db()
    assert exercise.kcals == 999
    assert not ActivityImport.objects.get(exercise=exercise).is_active
    assert exercise_writes == [exercise.pk]


@pytest.mark.django_db
@pytest.mark.parametrize("same_owner", [False, True])
def test_admin_can_move_imported_exercise(
    logged_in_admin_client, imported_activity, client, day_factory, same_owner
):
    """Changing the day remains supported, including another owner's day."""
    exercise, token, record = imported_activity
    old_day = exercise.day
    target = day_factory(
        day_num=2,
        day=datetime.date(2023, 1, 10),
        **({"plan": old_day.plan} if same_owner else {}),
    )
    response = logged_in_admin_client.post(
        f"/admin/exercises/exercise/{exercise.pk}/change/",
        _exercise_data(exercise, day=target.pk),
    )
    assert response.status_code == 302
    exercise.refresh_from_db()
    assert exercise.day_id == target.pk
    assert exercise.kcals == 999
    assert _replay(client, token, record)["unchanged"] == 1
    old_day.refresh_from_db()
    target.refresh_from_db()
    assert not old_day.exercises_flag
    assert target.exercises_flag


@pytest.mark.django_db
@pytest.mark.parametrize("bulk", [False, True])
def test_admin_delete_permanently_overrides_import(
    logged_in_admin_client, imported_activity, client, bulk, exercise_factory
):
    """Admin deletion must leave an inactive, detached tombstone."""
    exercise, token, record = imported_activity
    manual = exercise_factory()
    if bulk:
        response = logged_in_admin_client.post(
            "/admin/exercises/exercise/",
            {
                "action": "delete_selected",
                "post": "yes",
                "_selected_action": [manual.pk, exercise.pk],
            },
        )
        assert not Exercise.objects.filter(pk=manual.pk).exists()
    else:
        response = logged_in_admin_client.post(
            f"/admin/exercises/exercise/{exercise.pk}/delete/", {"post": "yes"}
        )
    assert response.status_code == 302
    assert _replay(client, token, record)["unchanged"] == 1
    assert not Exercise.objects.filter(pk=exercise.pk).exists()
    imported = ActivityImport.objects.get(
        source_record_id=record["source_record_id"]
    )
    assert not imported.is_active
    assert imported.exercise_id is None


def _form_data(form):
    data = {}
    for field in form:
        value = field.value()
        if isinstance(field.field.widget, forms.CheckboxInput):
            if value:
                data[field.html_name] = "on"
        else:
            data[field.html_name] = "" if value is None else value
    return data


def _inline_payload(response):
    data = _form_data(response.context["adminform"].form)
    formsets = [
        item.formset for item in response.context["inline_admin_formsets"]
    ]
    exercise_forms = []
    while formsets:
        formset = formsets.pop()
        data.update(_form_data(formset.management_form))
        for form in formset.forms:
            data.update(_form_data(form))
            formsets.extend(getattr(form, "nested_formsets", []))
            if formset.model is Exercise:
                exercise_forms.append(form)
    data["_save"] = "Save"
    return data, exercise_forms


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["day", "weekplan"])
@pytest.mark.parametrize("delete", [False, True])
def test_inline_override_survives_replay(
    logged_in_admin_client,
    imported_activity,
    client,
    parent,
    delete,
    exercise_writes,
):
    """Exercise inlines on both calendar admins preserve manual intent."""
    exercise, token, record = imported_activity
    parent_id = exercise.day_id if parent == "day" else exercise.day.plan_id
    url = f"/admin/plans/{parent}/{parent_id}/change/"
    response = logged_in_admin_client.get(url)
    assert response.status_code == 200
    data, exercise_forms = _inline_payload(response)
    form = next(
        form for form in exercise_forms if form.instance.pk == exercise.pk
    )
    data[form.add_prefix("DELETE" if delete else "kcals")] = (
        "on" if delete else 999
    )
    response = logged_in_admin_client.post(url, data)
    assert response.status_code == 302, response.context["errors"]
    assert _replay(client, token, record)["unchanged"] == 1
    assert exercise_writes == [exercise.pk]
    imported = ActivityImport.objects.get(
        source_record_id=record["source_record_id"]
    )
    assert not imported.is_active
    if delete:
        assert imported.exercise_id is None
        assert not Exercise.objects.filter(pk=exercise.pk).exists()
    else:
        exercise.refresh_from_db()
        assert exercise.kcals == 999


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["day", "weekplan"])
def test_inline_locks_owner_before_parent_write(
    logged_in_admin_client, imported_activity, parent, monkeypatch
):
    """The enclosing calendar save cannot invert importer lock ordering."""
    exercise, _token, _record_data = imported_activity
    parent_id = exercise.day_id if parent == "day" else exercise.day.plan_id
    url = f"/admin/plans/{parent}/{parent_id}/change/"
    data, exercise_forms = _inline_payload(logged_in_admin_client.get(url))
    data[exercise_forms[0].add_prefix("kcals")] = 999
    owners = set()
    original_fetch = QuerySet._fetch_all

    def fetch(queryset):
        result = original_fetch(queryset)
        if queryset.query.select_for_update:
            if queryset.model is User:
                owners.update(obj.pk for obj in queryset._result_cache)
            elif queryset.model in (Day, WeekPlan):
                assert exercise.day.plan.user_id in owners
        return result

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    original_save = WeekPlan.save

    def save(plan, *args, **kwargs):
        assert plan.user_id in owners
        return original_save(plan, *args, **kwargs)

    monkeypatch.setattr(WeekPlan, "save", save)
    response = logged_in_admin_client.post(url, data)
    assert response.status_code == 302


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["day", "weekplan"])
def test_unchanged_inline_keeps_import_active(
    logged_in_admin_client, imported_activity, client, parent
):
    """Saving unrelated calendar fields must not claim untouched exercises."""
    exercise, token, record = imported_activity
    parent_id = exercise.day_id if parent == "day" else exercise.day.plan_id
    url = f"/admin/plans/{parent}/{parent_id}/change/"
    data, _forms = _inline_payload(logged_in_admin_client.get(url))
    assert logged_in_admin_client.post(url, data).status_code == 302
    assert ActivityImport.objects.get(exercise=exercise).is_active
    assert _replay(client, token, record)["updated"] == 1
    exercise.refresh_from_db()
    assert exercise.kcals == 400


@pytest.mark.django_db
@pytest.mark.parametrize("parent", ["exercise", "day", "weekplan"])
def test_admin_still_creates_manual_exercises(
    logged_in_admin_client, imported_activity, parent
):
    """Standalone and inline creation remain editable without provenance."""
    exercise, _token, _record_data = imported_activity
    if parent == "exercise":
        url = "/admin/exercises/exercise/add/"
        data = _exercise_data(exercise, type="gym", duration="", distance="")
    else:
        parent_id = (
            exercise.day_id if parent == "day" else exercise.day.plan_id
        )
        url = f"/admin/plans/{parent}/{parent_id}/change/"
        data, exercise_forms = _inline_payload(logged_in_admin_client.get(url))
        prefix = exercise_forms[0].prefix.rsplit("-", 1)[0]
        index = int(data[f"{prefix}-TOTAL_FORMS"])
        data[f"{prefix}-TOTAL_FORMS"] = index + 1
        data.update(
            {
                f"{prefix}-{index}-{key}": value
                for key, value in {
                    "id": "",
                    "day": exercise.day_id,
                    "type": "gym",
                    "kcals": 999,
                    "duration": "",
                    "distance": "",
                }.items()
            }
        )
    response = logged_in_admin_client.post(url, data)
    assert response.status_code == 302, response.context["errors"]
    created = Exercise.objects.get(day=exercise.day, type="gym")
    assert created.kcals == 999
    assert created.duration is None
    assert created.distance is None
    assert not ActivityImport.objects.filter(exercise=created).exists()
    assert ActivityImport.objects.get(exercise=exercise).is_active


@pytest.mark.django_db
@pytest.mark.parametrize(
    "operation",
    [
        "edit",
        "delete",
        "bulk",
        "day",
        "weekplan",
        "day-delete",
        "weekplan-delete",
    ],
)
def test_admin_override_failure_rolls_back_every_write(
    logged_in_admin_client,
    imported_activity,
    operation,
    monkeypatch,
    exercise_factory,
):
    """Failure after a service write rolls back parent, exercise and tombstone."""
    from apps.exercises import admin as exercise_admin

    exercise, _token, _record_data = imported_activity
    extra = exercise_factory(day=exercise.day)
    before_exercises = list(Exercise.objects.order_by("pk").values())
    before_imports = list(ActivityImport.objects.values())
    before_days = list(Day.objects.order_by("pk").values())
    if operation in ("day", "weekplan", "day-delete", "weekplan-delete"):
        parent = operation.split("-")[0]
        parent_id = (
            exercise.day_id if parent == "day" else exercise.day.plan_id
        )
        url = f"/admin/plans/{parent}/{parent_id}/change/"
        data, exercise_forms = _inline_payload(logged_in_admin_client.get(url))
        for form in exercise_forms:
            data[
                form.add_prefix(
                    "DELETE" if operation.endswith("delete") else "kcals"
                )
            ] = ("on" if operation.endswith("delete") else 999)
    elif operation == "bulk":
        url = "/admin/exercises/exercise/"
        data = {
            "action": "delete_selected",
            "post": "yes",
            "_selected_action": [exercise.pk, extra.pk],
        }
    elif operation == "delete":
        url = f"/admin/exercises/exercise/{exercise.pk}/delete/"
        data = {"post": "yes"}
    else:
        url = f"/admin/exercises/exercise/{exercise.pk}/change/"
        data = _exercise_data(exercise)
    service_name = (
        "delete_manual_exercise"
        if "delete" in operation or operation == "bulk"
        else "update_manual_exercise"
    )
    original = getattr(exercise_admin, service_name)
    calls = []

    def fail_after_write(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(args[1])
        if operation != "bulk" or len(calls) == 2:
            raise RuntimeError("injected admin failure")
        return result

    monkeypatch.setattr(exercise_admin, service_name, fail_after_write)
    with pytest.raises(RuntimeError, match="injected admin failure"):
        logged_in_admin_client.post(url, data)
    assert list(Exercise.objects.order_by("pk").values()) == before_exercises
    assert list(ActivityImport.objects.values()) == before_imports
    assert list(Day.objects.order_by("pk").values()) == before_days


@pytest.mark.django_db
def test_week_admin_can_still_add_calendar(
    logged_in_admin_client, imported_activity
):
    """The inline-aware admin retains its existing week creation capability."""
    exercise, _token, _record_data = imported_activity
    plan = exercise.day.plan
    url = "/admin/plans/weekplan/add/"
    data, _forms = _inline_payload(logged_in_admin_client.get(url))
    start = plan.start_date + datetime.timedelta(days=7)
    data.update(
        {
            "user": plan.user_id,
            "measurement": plan.measurement_id,
            "start_date": start.isoformat(),
            "protein_g_kg": plan.protein_g_kg,
            "fat_perc": plan.fat_perc,
            "deficit": plan.deficit,
        }
    )
    response = logged_in_admin_client.post(url, data)
    assert response.status_code == 302, response.context["errors"]
    created = WeekPlan.objects.get(user=plan.user, start_date=start)
    assert Day.objects.filter(plan=created).count() == 7


@pytest.mark.django_db
def test_bulk_delete_locks_all_owners_before_any_exercise(
    logged_in_admin_client, imported_activity, exercise_factory, monkeypatch
):
    """A multi-owner selection acquires the full sorted owner set first."""
    exercise, _token, _record_data = imported_activity
    other = exercise_factory()
    expected_owners = sorted(
        {exercise.day.plan.user_id, other.day.plan.user_id}
    )
    owners = []
    queries = []
    original_fetch = QuerySet._fetch_all

    def fetch(queryset):
        fresh = queryset._result_cache is None
        result = original_fetch(queryset)
        if fresh and queryset.query.select_for_update:
            queries.append(queryset)
            if queryset.model is User:
                owners.extend(obj.pk for obj in queryset._result_cache)
            elif queryset.model is Exercise:
                assert owners[: len(expected_owners)] == expected_owners
        return result

    monkeypatch.setattr(QuerySet, "_fetch_all", fetch)
    response = logged_in_admin_client.post(
        "/admin/exercises/exercise/",
        {
            "action": "delete_selected",
            "post": "yes",
            "_selected_action": [other.pk, exercise.pk],
        },
    )
    assert response.status_code == 302
    assert any(query.model is Exercise for query in queries)
