"""Sync reuses the intake calendar without changing existing day settings."""

import datetime

import pytest
from django.db import connections
from django.utils import timezone

from apps.exercises.models import DaySteps, Exercise
from apps.health_sync import services
from apps.health_sync.models import (
    ActivityImport,
    HealthSyncDevice,
    StepImport,
    StepSyncWatermark,
)
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from tests.health_sync.test_api import post_json


@pytest.fixture
def calendar_template(user, measurement_factory, week_plan_factory):
    """Provide historical inputs for an absent current calendar week."""
    start = timezone.localdate() - datetime.timedelta(days=14)
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime.combine(
            start, datetime.time(), tzinfo=datetime.timezone.utc
        )
    )
    return week_plan_factory(
        user=user, measurement=measurement, start_date=start
    )


def _upload(client, token, date, kind):
    """Upload one stable observation, suitable for an exact retry."""
    observed = datetime.datetime.combine(
        date, datetime.time(), tzinfo=datetime.timezone.utc
    )
    if kind == "activities":
        record = {
            "source_record_id": "calendar-activity",
            "source_modified_at": observed.isoformat(),
            "start_time": observed.isoformat(),
            "end_time": (
                observed + datetime.timedelta(minutes=30)
            ).isoformat(),
            "type": "walk",
            "active_kcals": 300,
            "distance_km": 5.25,
        }
    else:
        record = {
            "date": date.isoformat(),
            "steps": 4321,
            "observed_at": observed.isoformat(),
        }
    return post_json(
        client,
        f"/api/health-sync/{kind}/",
        {"records": [record]},
        token,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_sync_creates_the_missing_calendar_and_retries_without_duplicates(
    client, calendar_template, kind
):
    """A real upload creates the anchored week and all seven days."""
    user = calendar_template.user
    token, _device = HealthSyncDevice.issue(user, "Phone")
    requested = timezone.localdate() - datetime.timedelta(days=1)
    original = list(calendar_template.days.order_by("pk").values())

    first = _upload(client, token, requested, kind)

    assert first.status_code == 200
    assert first.json()["summary"]["created"] == 1
    day = Day.objects.get(plan__user=user, day=requested)
    assert day.plan.start_date == requested - datetime.timedelta(days=6)
    assert day.plan.days.count() == 7
    assert day.plan.protein_g_kg == calendar_template.protein_g_kg
    assert day.plan.fat_perc == calendar_template.fat_perc
    assert day.plan.deficit == calendar_template.deficit
    if kind == "steps":
        assert DaySteps.objects.get(day=day).steps == 4321
    else:
        assert Exercise.objects.get(day=day).kcals == 300
    before_retry = list(Day.objects.order_by("pk").values())

    retry = _upload(client, token, requested, kind)

    assert retry.json()["summary"]["unchanged"] == 1
    assert WeekPlan.objects.filter(user=user).count() == 2
    assert list(Day.objects.order_by("pk").values()) == before_retry
    assert list(calendar_template.days.order_by("pk").values()) == original


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_sync_repairs_a_missing_day_without_overwriting_survivors(
    client, calendar_template, kind
):
    """The shared calendar service repairs the selected plan in place."""
    user = calendar_template.user
    token, _device = HealthSyncDevice.issue(user, "Phone")
    missing = calendar_template.days.get(day_num=3)
    requested = missing.day
    missing.delete()
    survivors = list(calendar_template.days.order_by("pk").values())

    response = _upload(client, token, requested, kind)

    assert response.json()["summary"]["created"] == 1
    assert calendar_template.days.count() == 7
    assert WeekPlan.objects.filter(user=user).count() == 1
    assert (
        list(
            calendar_template.days.exclude(day=requested)
            .order_by("pk")
            .values()
        )
        == survivors
    )


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_existing_day_keeps_settings_and_does_not_resolve_calendar(
    client, calendar_template, kind, mocker
):
    """An explicit existing day remains authoritative for legacy calendars."""
    day = calendar_template.days.get(day_num=3)
    token, _device = HealthSyncDevice.issue(calendar_template.user, "Phone")
    Day.objects.filter(pk=day.pk).update(tracked=False, deficit=42)
    day.refresh_from_db()
    # Exercise saves intentionally enable tracking through the existing signal.
    settings = (
        day.plan_id,
        day.day,
        day.day_num,
        kind == "activities",
        day.deficit,
    )
    resolver = mocker.patch("apps.health_sync.services.ensure_day")

    assert (
        _upload(client, token, day.day, kind).json()["summary"]["created"] == 1
    )

    day.refresh_from_db()
    assert (
        day.plan_id,
        day.day,
        day.day_num,
        day.tracked,
        day.deficit,
    ) == settings
    resolver.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_missing_owner_plan_skips_without_using_another_users_template(
    client, calendar_template, user_factory, kind
):
    """A different owner's historical defaults cannot initialize this user."""
    owner = user_factory()
    token, device = HealthSyncDevice.issue(owner, "Phone")
    before = list(Day.objects.order_by("pk").values())
    requested = timezone.localdate() - datetime.timedelta(days=1)

    response = _upload(client, token, requested, kind)

    assert response.status_code == 200
    assert response.json()["summary"]["skipped"] == 1
    assert not WeekPlan.objects.filter(user=owner).exists()
    assert list(Day.objects.order_by("pk").values()) == before
    device.refresh_from_db()
    assert device.last_success_at is None
    assert not DaySteps.objects.exists()
    assert not Exercise.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_unauthenticated_sync_cannot_create_calendar(
    client, calendar_template, kind
):
    """Authentication fails before any calendar write."""
    before = list(Day.objects.order_by("pk").values())
    requested = timezone.localdate() - datetime.timedelta(days=1)

    assert _upload(client, None, requested, kind).status_code == 401

    assert list(Day.objects.order_by("pk").values()) == before
    assert WeekPlan.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_calendar_and_import_roll_back_together(
    client, calendar_template, kind, mocker
):
    """A failed provenance write rolls back the new calendar and data."""
    token, device = HealthSyncDevice.issue(calendar_template.user, "Phone")
    requested = timezone.localdate() - datetime.timedelta(days=1)
    before = list(Day.objects.order_by("pk").values())
    model = StepImport if kind == "steps" else ActivityImport
    mocker.patch.object(
        model, "save", side_effect=RuntimeError("write failed")
    )

    with pytest.raises(RuntimeError, match="write failed"):
        _upload(client, token, requested, kind)

    assert list(Day.objects.order_by("pk").values()) == before
    assert WeekPlan.objects.count() == 1
    assert not DaySteps.objects.exists()
    assert not Exercise.objects.exists()
    assert not StepImport.objects.exists()
    assert not ActivityImport.objects.exists()
    assert not StepSyncWatermark.objects.exists()
    device.refresh_from_db()
    assert device.last_success_at is None


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_calendar_failure_rolls_back_and_can_be_retried(
    client, calendar_template, kind, mocker
):
    """Calendar validation failures do not commit partial days or provenance."""
    token, _device = HealthSyncDevice.issue(calendar_template.user, "Phone")
    requested = timezone.localdate() - datetime.timedelta(days=1)
    before = list(Day.objects.order_by("pk").values())
    original = services.ensure_day

    def fail_after_creation(*args, **kwargs):
        original(*args, **kwargs)
        raise ValueError("invalid calendar")

    resolver = mocker.patch(
        "apps.health_sync.services.ensure_day", side_effect=fail_after_creation
    )
    response = _upload(client, token, requested, kind)
    assert response.status_code == 200
    assert response.json()["summary"]["skipped"] == 1
    assert list(Day.objects.order_by("pk").values()) == before
    assert WeekPlan.objects.count() == 1
    assert not StepSyncWatermark.objects.exists()
    assert not ActivityImport.objects.exists()
    resolver.side_effect = original

    assert (
        _upload(client, token, requested, kind).json()["summary"]["created"]
        == 1
    )


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["steps", "activities"])
def test_calendar_resolution_follows_owner_lock_inside_transaction(
    client, calendar_template, kind, mocker
):
    """Calendar locks never precede the canonical owner lock in either sync."""
    token, _device = HealthSyncDevice.issue(calendar_template.user, "Phone")
    requested = timezone.localdate() - datetime.timedelta(days=1)
    lock_owner = mocker.spy(services, "lock_plan_owner")
    original = services.ensure_day

    def ensure_locked(user, date):
        lock_owner.assert_called_once_with(using="default", user_id=user.pk)
        assert connections["default"].in_atomic_block
        return original(user, date)

    resolver = mocker.patch(
        "apps.health_sync.services.ensure_day", side_effect=ensure_locked
    )

    assert (
        _upload(client, token, requested, kind).json()["summary"]["created"]
        == 1
    )
    resolver.assert_called_once()
