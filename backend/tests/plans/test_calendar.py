"""On-demand calendar creation contract tests."""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models.query import QuerySet

from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from apps.plans.services import ensure_day, ensure_week


def test_template_is_locked_before_reading_targets(db, week_plan, mocker):
    """Template targets must be read under the plan lock, not before it."""
    # Inspect Django's evaluation internals to catch pre-lock target reads.
    # pylint: disable=protected-access
    original = QuerySet._fetch_all

    def check_lock(queryset):
        if queryset.model is WeekPlan and queryset._result_cache is None:
            assert (
                queryset.query.select_for_update
            ), "template read without lock"
        return original(queryset)

    mocker.patch.object(QuerySet, "_fetch_all", check_lock)
    assert ensure_week(week_plan.user, week_plan.start_date).pk == week_plan.pk


@pytest.mark.django_db(transaction=True)
def test_week_and_generated_days_roll_back_together(
    user, measurement_factory, mocker
):
    """A signal failure cannot leave an empty or partially generated plan."""
    measurement = measurement_factory(user=user)
    original = Day.save

    def fail_third(day, *args, **kwargs):
        if day.day_num == 3:
            raise RuntimeError("injected day failure")
        return original(day, *args, **kwargs)

    mocker.patch.object(Day, "save", fail_third)
    with pytest.raises(RuntimeError, match="injected day failure"):
        WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=datetime.date(2023, 1, 11),
            protein_g_kg=Decimal("2.0"),
            fat_perc=Decimal("25"),
            deficit=0,
        )
    assert not WeekPlan.objects.filter(user=user).exists()
    assert not Day.objects.filter(plan__user=user).exists()


@pytest.mark.parametrize("key", ["week", "day", "day_num"])
def test_calendar_identity_is_database_unique(
    db, week_plan, week_plan_factory, key
):
    """Even writers bypassing services cannot duplicate a calendar key."""
    if key == "week":
        other = week_plan_factory(
            user=week_plan.user, start_date=datetime.date(2023, 2, 1)
        )
        queryset = WeekPlan.objects.filter(pk=other.pk)
        changes = {"start_date": week_plan.start_date}
    else:
        queryset = week_plan.days.filter(day_num=2)
        changes = {key: week_plan.start_date if key == "day" else 1}
    with pytest.raises(IntegrityError), transaction.atomic():
        queryset.update(**changes)


@pytest.mark.parametrize("missing", ["template", "measurement"])
def test_missing_historical_inputs_are_explicit_errors(
    db, user, measurement_factory, week_plan_factory, missing
):
    """Future targets and physiology must not initialize a historical week."""
    measurement = measurement_factory(user=user)
    if missing == "measurement":
        week_plan_factory(user=user, measurement=measurement)
    else:
        week_plan_factory(
            user=user,
            measurement=measurement,
            start_date=datetime.date(2023, 3, 1),
        )
    before = (WeekPlan.objects.count(), Day.objects.count())
    with pytest.raises(
        ValueError,
        match=(
            "Create a week plan" if missing == "template" else "No measurement"
        ),
    ):
        ensure_day(user, datetime.date(2023, 2, 4))
    assert (WeekPlan.objects.count(), Day.objects.count()) == before


def test_repair_preserves_every_existing_day_value(
    db, week_plan, intake_factory
):
    """Repair missing days without saving existing rows or recalculating goals."""
    retained = week_plan.days.get(day_num=1)
    intake = intake_factory(day=retained)
    Day.objects.filter(pk=retained.pk).update(
        energy_kcal_goal=Decimal("123.45")
    )
    snapshot = list(week_plan.days.exclude(day_num=3).order_by("pk").values())
    missing_date = week_plan.days.get(day_num=3).day
    week_plan.days.filter(day_num=3).delete()
    repaired = ensure_day(week_plan.user, retained.day)
    assert repaired.pk == retained.pk
    assert week_plan.days.count() == 7
    assert week_plan.days.get(day=missing_date).day_num == 3
    assert (
        list(week_plan.days.exclude(day_num=3).order_by("pk").values())
        == snapshot
    )
    assert retained.intakes.get().pk == intake.pk
    before = list(week_plan.days.order_by("pk").values())
    assert ensure_week(week_plan.user, missing_date).pk == week_plan.pk
    assert list(week_plan.days.order_by("pk").values()) == before


def test_ensure_day_extends_the_existing_week_anchor(
    db, user, measurement_factory, week_plan_factory
):
    """A requested date creates only its anchored week, with historical inputs."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    template = week_plan_factory(
        user=user,
        measurement=measurement,
        start_date=datetime.date(2023, 1, 11),
    )
    requested = datetime.date(2023, 2, 4)
    day = ensure_day(user, requested)
    assert day.day == requested
    assert day.plan.start_date == datetime.date(2023, 2, 1)
    assert day.plan.measurement_id == measurement.pk
    assert day.plan.protein_g_kg == template.protein_g_kg
    assert day.plan.fat_perc == template.fat_perc
    assert day.plan.deficit == template.deficit
    assert day.tracked is True
    assert list(
        day.plan.days.order_by("day_num").values_list(
            "day_num", "deficit", flat=False
        )
    ) == [(1, 180), (2, 160), (3, 180), (4, 220), (5, 220), (6, 220), (7, 220)]
    assert WeekPlan.objects.filter(user=user).count() == 2
    assert Day.objects.filter(plan__user=user).count() == 14


@pytest.mark.parametrize("scenario", ["new_overlap", "ambiguous_existing"])
def test_date_resolution_rejects_overlapping_weeks(
    db, user, measurement_factory, week_plan_factory, scenario
):
    """Date-only logging must not choose or create overlapping calendar windows."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    first = week_plan_factory(
        user=user,
        measurement=measurement,
        start_date=datetime.date(2023, 1, 11),
    )
    later_start = datetime.date(2023, 2, 3)
    requested = datetime.date(2023, 2, 2)
    if scenario == "ambiguous_existing":
        later_start = first.start_date + datetime.timedelta(days=3)
        requested = later_start
    later = week_plan_factory(
        user=user, measurement=measurement, start_date=later_start
    )
    # Ambiguity is about plan windows, even if the requested day is missing.
    later.days.filter(day_num=1).delete()
    before = (list(WeekPlan.objects.values()), list(Day.objects.values()))
    with pytest.raises(ValueError, match="Overlapping week plans"):
        ensure_day(user, requested)
    assert (
        list(WeekPlan.objects.values()),
        list(Day.objects.values()),
    ) == before


def test_waiting_creator_reuses_week_committed_after_template_read(
    db, user, measurement_factory, week_plan_factory, mocker
):
    """A contender's exact window is a retry, not a legacy overlap conflict."""
    measurement = measurement_factory(user=user)
    Measurement.objects.filter(pk=measurement.pk).update(
        created_at=datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    )
    week_plan_factory(user=user, measurement=measurement)
    original = QuerySet.exists
    committed = []

    def commit_competing_week(queryset):
        if queryset.model is WeekPlan and not committed:
            committed.append(
                week_plan_factory(
                    user=user,
                    measurement=measurement,
                    start_date=datetime.date(2023, 2, 6),
                    deficit=321,
                )
            )
        return original(queryset)

    mocker.patch.object(QuerySet, "exists", commit_competing_week)
    day = ensure_day(user, datetime.date(2023, 2, 7))
    assert day.plan_id == committed[0].pk
    assert day.plan.deficit == 321
    assert day.plan.days.count() == 7
    assert WeekPlan.objects.filter(user=user).count() == 2
