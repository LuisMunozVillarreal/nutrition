"""On-demand calendar creation shared by application writers."""

import datetime
from decimal import Decimal

from django.db import router, transaction

from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from apps.plans.validation import validated_week_plan_parameters
from apps.users.models import User


def ensure_week(user: User, date: datetime.date) -> WeekPlan:
    """Return the requested seven-day plan using the user's existing anchor.

    Args:
        user (User): Owner whose established targets may be copied.
        date (datetime.date): Requested calendar date.

    Returns:
        WeekPlan: Existing or newly created complete week.

    Raises:
        ValueError: If historical inputs are missing or week windows overlap.
    """
    using = router.db_for_write(WeekPlan, instance=user)
    with transaction.atomic(using=using):
        # Discover only immutable identity/anchor fields before taking locks.
        # Creation and measurement updates both lock Measurement -> Plan -> Day;
        # taking the template first would invert its new plan's deferred FK lock.
        anchor = (
            WeekPlan.objects.using(using)
            .filter(user=user, start_date__lte=date)
            .order_by("-start_date", "-pk")
            .values_list("pk", "start_date", "measurement_id")
            .first()
        )
        if anchor is None:
            raise ValueError(
                "Create a week plan on or before the requested date first"
            )
        template_id, template_start, measurement_id = anchor
        start = template_start + datetime.timedelta(
            days=((date - template_start).days // 7) * 7
        )
        measurements = Measurement.objects.using(using).select_for_update(
            of=("self",)
        )
        if start == template_start:
            measurements = measurements.filter(pk=measurement_id)
        else:
            measurements = measurements.filter(
                user=user, created_at__date__lte=start
            )
        measurement = measurements.order_by("-created_at", "-pk").first()
        if measurement is None:
            raise ValueError(
                "No measurement available on or before the week start"
            )
        template = (
            WeekPlan.objects.using(using)
            .select_for_update(of=("self",))
            .get(pk=template_id)
        )
        # A whole generated week must fit, not just the requested date. Legacy
        # overlaps require an explicit day ID; never choose or merge their data.
        if (
            WeekPlan.objects.using(using)
            .filter(
                user=user,
                start_date__gt=start - datetime.timedelta(days=7),
                start_date__lt=start + datetime.timedelta(days=7),
            )
            # A concurrent creator may have committed this exact window while
            # we waited for the template lock. Re-resolve that target below.
            .exclude(start_date=start)
            .exists()
        ):
            raise ValueError(
                "Overlapping week plans; select an explicit day ID"
            )
        if start == template.start_date:
            ensure_week_days(template)
            return template
        # Re-resolve after waiting for locks: an exact target can have its own
        # valid settings even when the historical creation defaults are invalid.
        plan = (
            WeekPlan.objects.using(using)
            .select_for_update(of=("self",))
            .filter(user=user, start_date=start)
            .first()
        )
        if plan is not None:
            ensure_week_days(plan)
            return plan
        protein_g_kg, fat_perc, deficit = validated_week_plan_parameters(
            measurement,
            float(template.protein_g_kg),
            float(template.fat_perc),
            template.deficit,
        )
        plan, _ = WeekPlan.objects.using(using).get_or_create(
            user=user,
            start_date=start,
            defaults={
                "measurement": measurement,
                "protein_g_kg": protein_g_kg,
                "fat_perc": fat_perc,
                "deficit": deficit,
            },
        )
        ensure_week_days(plan)
        return plan


def ensure_week_days(plan: WeekPlan) -> None:
    """Fill absent dates from the plan's own targets without resaving survivors.

    Args:
        plan (WeekPlan): Exact plan to repair under its row lock.
    """
    using = router.db_for_write(WeekPlan, instance=plan)
    with transaction.atomic(using=using):
        plan = (
            WeekPlan.objects.using(using).select_for_update().get(pk=plan.pk)
        )
        existing_dates = set(
            plan.days.using(using).values_list("day", flat=True)
        )
        missing_days = [
            Day(
                plan=plan,
                day=plan.start_date + datetime.timedelta(days=num),
                day_num=num + 1,
                deficit=plan.deficit * plan.DEFICIT_DISTRIBUTION[num] / 100,
            )
            for num in range(plan.PLAN_LENGTH_DAYS)
            if plan.start_date + datetime.timedelta(days=num)
            not in existing_dates
        ]
        if not missing_days:
            return
        # The plan lock serializes repair with measurement/target updates.
        # Validate only absent siblings, with their own default tracking mode,
        # before any insert or signal can change the plan or its survivors.
        validated_week_plan_parameters(
            plan.measurement,
            float(plan.protein_g_kg),
            float(plan.fat_perc),
            plan.deficit,
            [day.tdee for day in missing_days],
            [Decimal(day.deficit) for day in missing_days],
        )
        for day in missing_days:
            Day.objects.using(using).get_or_create(
                plan=plan,
                day=day.day,
                defaults={"day_num": day.day_num, "deficit": day.deficit},
            )


def resolve_day(user: User, day_id: int | None, day_date: str | None) -> Day:
    """Resolve an owned logging day from an ID or an explicit calendar date.

    Args:
        user (User): Authenticated owner, checked by the calling mutation.
        day_id (int | None): Exact existing day, preserving its plan selection.
        day_date (str | None): ISO calendar date to ensure on demand.

    Returns:
        Day: Owned day with a complete parent week.

    Raises:
        ValueError: If selectors are ambiguous, invalid, missing or unowned.
    """
    if (day_id is None) == (day_date is None):
        raise ValueError("Provide exactly one of dayId or dayDate")
    if day_date is not None:
        return ensure_day(user, datetime.date.fromisoformat(day_date))
    try:
        day = Day.objects.select_related("plan").get(
            pk=day_id, plan__user=user
        )
    except Day.DoesNotExist as exc:
        raise ValueError("Day not found") from exc
    ensure_week_days(day.plan)
    return day


def ensure_day(user: User, date: datetime.date) -> Day:
    """Return the requested day, creating its complete week on demand.

    Args:
        user (User): Owner with an existing historical plan template.
        date (datetime.date): Calendar date to resolve.

    Returns:
        Day: Requested day in the ensured week.
    """
    return ensure_week(user, date).days.get(day=date)
