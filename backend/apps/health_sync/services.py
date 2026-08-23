"""Daily step import validation and transactional upsert service."""

# Public service functions have concise behavioral docstrings; validation
# branches intentionally share stable ValueError responses.
# pylint: disable=missing-param-doc,missing-return-doc,missing-raises-doc

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any

from django.db import router, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.exercises.models import DaySteps
from apps.health_sync.models import (
    HealthSyncDevice,
    StepImport,
    StepSyncWatermark,
)
from apps.plans.locks import lock_plan_aggregate_rows, lock_plan_owner
from apps.plans.models import Day

MAX_RECORDS = 31
MAX_STEPS_PER_DAY = 1_000_000
MAX_DATE_LOOKBACK_DAYS = 30
MAX_DATE_AHEAD_DAYS = 1
CANONICAL_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


@dataclass(frozen=True)
class DailyStepRecord:
    """Validated daily aggregate supplied by Health Connect."""

    date: datetime.date
    steps: int
    observed_at: datetime.datetime


def _parse_local_date(raw: dict[str, Any]) -> datetime.date:
    """Parse only the canonical public ``YYYY-MM-DD`` representation."""
    raw_date = raw.get("date")
    if not isinstance(raw_date, str) or not CANONICAL_DATE.fullmatch(raw_date):
        raise ValueError("date must use YYYY-MM-DD")
    try:
        return datetime.date.fromisoformat(raw_date)
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc


def parse_records(payload: Any) -> list[DailyStepRecord]:
    """Validate an ingestion payload before performing any database writes."""
    if not isinstance(payload, dict) or not isinstance(
        payload.get("records"), list
    ):
        raise ValueError("records must be a list")
    raw_records = payload["records"]
    if len(raw_records) > MAX_RECORDS:
        raise ValueError(f"records must contain at most {MAX_RECORDS} items")

    parsed: list[DailyStepRecord] = []
    seen_dates: set[datetime.date] = set()
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError("each record must be an object")
        local_date = _parse_local_date(raw)
        if local_date in seen_dates:
            raise ValueError("records must contain unique dates")
        seen_dates.add(local_date)
        server_date = timezone.localdate()
        if local_date < server_date - datetime.timedelta(
            days=MAX_DATE_LOOKBACK_DAYS
        ):
            raise ValueError("date is outside the supported sync window")
        if local_date > server_date + datetime.timedelta(
            days=MAX_DATE_AHEAD_DAYS
        ):
            raise ValueError("date cannot be in the future")

        steps = raw.get("steps")
        if isinstance(steps, bool) or not isinstance(steps, int):
            raise ValueError("steps must be an integer")
        if not 0 <= steps <= MAX_STEPS_PER_DAY:
            raise ValueError(
                f"steps must be between 0 and {MAX_STEPS_PER_DAY}"
            )

        raw_observed = raw.get("observed_at", "")
        if not isinstance(raw_observed, str):
            raise ValueError(
                "observed_at must be an ISO-8601 timestamp with timezone"
            )
        observed_at = parse_datetime(raw_observed)
        if observed_at is None or timezone.is_naive(observed_at):
            raise ValueError(
                "observed_at must be an ISO-8601 timestamp with timezone"
            )
        if observed_at > timezone.now() + datetime.timedelta(minutes=5):
            raise ValueError("observed_at cannot be in the future")
        parsed.append(DailyStepRecord(local_date, steps, observed_at))
    return parsed


def sync_records(
    device: HealthSyncDevice,
    records: list[DailyStepRecord],
) -> dict[str, Any]:
    """Upsert fresh daily totals into days belonging to the device owner."""
    summary = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    results: list[dict[str, str]] = []
    using = router.db_for_write(DaySteps)

    for record in records:
        with transaction.atomic(using=using):
            locked_user = lock_plan_owner(using=using, user_id=device.user_id)
            day_ids = list(
                Day.objects.using(using)
                .filter(
                    plan__user=locked_user,
                    day=record.date,
                )
                .values_list("pk", flat=True)[:2]
            )
            if len(day_ids) != 1:
                summary["skipped"] += 1
                results.append(
                    {"date": record.date.isoformat(), "status": "skipped"}
                )
                continue
            aggregate_locks = lock_plan_aggregate_rows(
                using=using, day_ids=day_ids
            )
            revalidated_day_ids = list(
                Day.objects.using(using)
                .filter(plan__user=locked_user, day=record.date)
                .values_list("pk", flat=True)[:2]
            )
            day = aggregate_locks.days_by_pk.get(day_ids[0])
            if revalidated_day_ids != day_ids or day is None:
                aggregate_locks.clear_markers()
                summary["skipped"] += 1
                results.append(
                    {"date": record.date.isoformat(), "status": "skipped"}
                )
                continue
            try:
                day_steps = (
                    DaySteps.objects.select_for_update()
                    .using(using)
                    .filter(day=day)
                    .first()
                )
                if day_steps is not None:
                    # Preserve the locked Day instance for post-save signals.
                    day_steps.day = day
                watermark = (
                    StepSyncWatermark.objects.select_for_update()
                    .using(using)
                    .filter(user_id=device.user_id, date=record.date)
                    .first()
                )
                if (
                    watermark is not None
                    and record.observed_at <= watermark.observed_at
                ):
                    summary["unchanged"] += 1
                    results.append(
                        {
                            "date": record.date.isoformat(),
                            "status": "unchanged",
                        }
                    )
                    continue

                if day_steps is not None and day_steps.steps == record.steps:
                    # Advance the idempotency watermark without a no-op write.
                    StepSyncWatermark.objects.using(using).update_or_create(
                        user_id=device.user_id,
                        date=record.date,
                        defaults={"observed_at": record.observed_at},
                    )
                    summary["unchanged"] += 1
                    results.append(
                        {
                            "date": record.date.isoformat(),
                            "status": "unchanged",
                        }
                    )
                    continue

                created = day_steps is None
                if day_steps is None:
                    day_steps = DaySteps.objects.using(using).create(
                        day=day, steps=record.steps
                    )
                else:
                    day_steps.steps = record.steps
                    day_steps.save(
                        using=using, update_fields=["steps", "updated_at"]
                    )

                StepImport.objects.using(using).update_or_create(
                    day_steps=day_steps,
                    defaults={
                        "device": device,
                        "source": StepImport.SOURCE_HEALTH_CONNECT,
                        "observed_at": record.observed_at,
                        "is_active": True,
                    },
                )
                StepSyncWatermark.objects.using(using).update_or_create(
                    user_id=device.user_id,
                    date=record.date,
                    defaults={"observed_at": record.observed_at},
                )
                status = "created" if created else "updated"
                summary[status] += 1
                results.append(
                    {"date": record.date.isoformat(), "status": status}
                )
            finally:
                aggregate_locks.clear_markers()

    return {"summary": summary, "records": results}


def create_manual_day_steps(user: Any, day_id: int, steps: int) -> DaySteps:
    """Create manual steps under the same canonical locks used by sync."""
    using = router.db_for_write(DaySteps)
    with transaction.atomic(using=using):
        locked_user = lock_plan_owner(using=using, user_id=user.pk)
        day_ids = list(
            Day.objects.using(using)
            .filter(pk=day_id, plan__user=locked_user)
            .values_list("pk", flat=True)[:1]
        )
        if not day_ids:
            raise ValueError("Day not found")
        locks = lock_plan_aggregate_rows(using=using, day_ids=day_ids)
        day = locks.days_by_pk.get(day_ids[0])
        try:
            still_owned = (
                Day.objects.using(using)
                .filter(pk=day_id, plan__user=locked_user)
                .exists()
            )
            if day is None or not still_owned:
                raise ValueError("Day not found")
            if (
                DaySteps.objects.select_for_update()
                .using(using)
                .filter(day=day)
                .exists()
            ):
                raise ValueError("Day steps already exist")
            return DaySteps.objects.using(using).create(day=day, steps=steps)
        finally:
            locks.clear_markers()


def update_manual_day_steps(
    user: Any, day_steps_id: int, steps: int
) -> DaySteps:
    """Update steps and remove import provenance in one locked transaction."""
    using = router.db_for_write(DaySteps)
    day_id = (
        DaySteps.objects.using(using)
        .filter(pk=day_steps_id, day__plan__user=user)
        .values_list("day_id", flat=True)
        .first()
    )
    if day_id is None:
        raise ValueError("Day steps not found")
    with transaction.atomic(using=using):
        lock_plan_owner(using=using, user_id=user.pk)
        locks = lock_plan_aggregate_rows(using=using, day_ids=(day_id,))
        day = locks.days_by_pk.get(day_id)
        try:
            if day is None:
                raise ValueError("Day steps not found")
            try:
                day_steps = (
                    DaySteps.objects.select_for_update()
                    .using(using)
                    .get(pk=day_steps_id, day=day)
                )
            except DaySteps.DoesNotExist as exc:
                raise ValueError("Day steps not found") from exc
            day_steps.day = day
            day_steps.steps = steps
            day_steps.save(
                using=using,
                update_fields=["steps", "updated_at"],
            )
            StepImport.objects.using(using).filter(day_steps=day_steps).update(
                is_active=False,
                updated_at=timezone.now(),
            )
            return day_steps
        finally:
            locks.clear_markers()


def delete_manual_day_steps(user: Any, day_steps_id: int) -> None:
    """Delete manual steps under the canonical aggregate lock order."""
    using = router.db_for_write(DaySteps)
    day_id = (
        DaySteps.objects.using(using)
        .filter(pk=day_steps_id, day__plan__user=user)
        .values_list("day_id", flat=True)
        .first()
    )
    if day_id is None:
        raise ValueError("Day steps not found")
    with transaction.atomic(using=using):
        lock_plan_owner(using=using, user_id=user.pk)
        locks = lock_plan_aggregate_rows(using=using, day_ids=(day_id,))
        day = locks.days_by_pk.get(day_id)
        try:
            if day is None:
                raise ValueError("Day steps not found")
            try:
                day_steps = (
                    DaySteps.objects.select_for_update()
                    .using(using)
                    .get(pk=day_steps_id, day=day)
                )
            except DaySteps.DoesNotExist as exc:
                raise ValueError("Day steps not found") from exc
            day_steps.day = day
            day_steps.delete(using=using)
        finally:
            locks.clear_markers()
