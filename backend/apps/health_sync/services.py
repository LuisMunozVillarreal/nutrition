"""Daily step import validation and transactional upsert service."""

# Public service functions have concise behavioral docstrings; validation
# branches intentionally share stable ValueError responses.
# pylint: disable=missing-param-doc,missing-return-doc,missing-raises-doc

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from django.db import router, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.exercises.models import DaySteps, Exercise
from apps.health_sync.models import (
    ActivityImport,
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

MAX_ACTIVITY_RECORDS = 100
MAX_ACTIVE_KCALS = 100_000
MAX_ACTIVITY_DURATION = datetime.timedelta(hours=24)
MAX_ACTIVITY_DISTANCE = Decimal("99999999.99")
MAX_SOURCE_RECORD_ID_LENGTH = 255
EXERCISE_TYPES = tuple(choice[0] for choice in Exercise.EXERCISE_CHOICES)


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


@dataclass(frozen=True)
class ActivityRecord:  # pylint: disable=too-many-instance-attributes
    """Validated exercise activity supplied by the Garmin companion."""

    source_record_id: str
    source_modified_at: datetime.datetime
    date: datetime.date
    time: datetime.time
    duration: datetime.timedelta
    exercise_type: str
    active_kcals: int
    distance: Decimal | None


def _parse_aware_timestamp(raw: Any, field_name: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp that must carry an explicit timezone."""
    if not isinstance(raw, str):
        raise ValueError(
            f"{field_name} must be an ISO-8601 timestamp with timezone"
        )
    parsed = parse_datetime(raw)
    if parsed is None or timezone.is_naive(parsed):
        raise ValueError(
            f"{field_name} must be an ISO-8601 timestamp with timezone"
        )
    return parsed


def _parse_distance(raw_distance: Any) -> Decimal | None:
    """Validate and round Health Connect distance to model precision."""
    if raw_distance is None:
        return None
    if isinstance(raw_distance, bool):
        raise ValueError("distance_km must be a finite number")
    if isinstance(raw_distance, int):
        value = Decimal(raw_distance)
    elif isinstance(raw_distance, float):
        if not math.isfinite(raw_distance):
            raise ValueError("distance_km must be a finite number")
        value = Decimal(str(raw_distance))
    else:
        raise ValueError("distance_km must be a finite number")
    if value < 0:
        raise ValueError("distance_km must be greater than or equal to 0")
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value > MAX_ACTIVITY_DISTANCE:
        raise ValueError(
            "distance_km must be less than or equal to "
            f"{MAX_ACTIVITY_DISTANCE}"
        )
    return value


def parse_activity_records(  # pylint: disable=too-many-branches
    payload: Any,
) -> list[ActivityRecord]:
    """Validate an activity batch before any database writes happen."""
    if not isinstance(payload, dict) or not isinstance(
        payload.get("records"), list
    ):
        raise ValueError("records must be a list")
    raw_records = payload["records"]
    if len(raw_records) > MAX_ACTIVITY_RECORDS:
        raise ValueError(
            f"records must contain at most {MAX_ACTIVITY_RECORDS} items"
        )

    parsed: list[ActivityRecord] = []
    seen_ids: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError("each record must be an object")

        source_record_id = raw.get("source_record_id")
        if (
            not isinstance(source_record_id, str)
            or not source_record_id.strip()
            or len(source_record_id) > MAX_SOURCE_RECORD_ID_LENGTH
        ):
            raise ValueError(
                "source_record_id must be a string of 1 to 255 characters"
            )
        if source_record_id in seen_ids:
            raise ValueError(
                "records must contain unique source_record_id values"
            )
        seen_ids.add(source_record_id)

        source_modified_at = _parse_aware_timestamp(
            raw.get("source_modified_at"), "source_modified_at"
        )
        if source_modified_at > timezone.now() + datetime.timedelta(minutes=5):
            raise ValueError("source_modified_at cannot be in the future")

        start_time = _parse_aware_timestamp(
            raw.get("start_time"), "start_time"
        )
        end_time = _parse_aware_timestamp(raw.get("end_time"), "end_time")
        if start_time >= end_time:
            raise ValueError("start_time must be before end_time")
        duration = end_time - start_time
        if duration > MAX_ACTIVITY_DURATION:
            raise ValueError("duration must not exceed 24 hours")

        # Derive the session day and wall-clock time from the offset embedded in
        # the uploaded start_time, not from the server's configured timezone.
        session_date = start_time.date()
        server_date = timezone.localdate()
        if session_date > server_date + datetime.timedelta(
            days=MAX_DATE_AHEAD_DAYS
        ):
            raise ValueError("activity cannot be in the future")

        exercise_type = raw.get("type")
        if exercise_type not in EXERCISE_TYPES:
            raise ValueError("type must be one of: walk, run, cycle, gym")

        active_kcals = raw.get("active_kcals")
        if isinstance(active_kcals, bool) or not isinstance(active_kcals, int):
            raise ValueError("active_kcals must be an integer")
        if not 0 <= active_kcals <= MAX_ACTIVE_KCALS:
            raise ValueError(
                f"active_kcals must be between 0 and {MAX_ACTIVE_KCALS}"
            )

        distance = _parse_distance(raw.get("distance_km"))

        parsed.append(
            ActivityRecord(
                source_record_id=source_record_id,
                source_modified_at=source_modified_at,
                date=session_date,
                time=start_time.time(),
                duration=duration,
                exercise_type=exercise_type,
                active_kcals=active_kcals,
                distance=distance,
            )
        )
    return parsed


def _exercise_matches(exercise: Exercise, record: ActivityRecord) -> bool:
    """Return whether an exercise already holds the record's exact values."""
    return (
        exercise.type == record.exercise_type
        and exercise.kcals == record.active_kcals
        and exercise.duration == record.duration
        and exercise.distance == record.distance
        and exercise.time == record.time
    )


def _save_import(
    import_row: ActivityImport,
    *,
    using: str,
    device: HealthSyncDevice,
    record: ActivityRecord,
    exercise: Exercise | None = None,
) -> None:
    """Advance import provenance to the accepted record without extra writes."""
    update_fields = ["device", "source_modified_at", "is_active", "updated_at"]
    if exercise is not None:
        import_row.exercise = exercise
        update_fields.append("exercise")
    import_row.device = device
    import_row.source_modified_at = record.source_modified_at
    import_row.is_active = True
    import_row.save(using=using, update_fields=update_fields)


# pylint: disable=too-many-branches,too-many-statements
def sync_activity_records(
    device: HealthSyncDevice,
    records: list[ActivityRecord],
) -> dict[str, Any]:
    """Upsert fresh activities into days owned by the device owner."""
    summary = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    results: list[dict[str, str]] = []
    using = router.db_for_write(Exercise)

    for record in records:
        if record.date < timezone.localdate() - datetime.timedelta(
            days=MAX_DATE_LOOKBACK_DAYS
        ):
            summary["skipped"] += 1
            results.append(
                {
                    "source_record_id": record.source_record_id,
                    "status": "skipped",
                }
            )
            continue
        with transaction.atomic(using=using):
            locked_user = lock_plan_owner(using=using, user_id=device.user_id)
            day_ids = list(
                Day.objects.using(using)
                .filter(plan__user=locked_user, day=record.date)
                .values_list("pk", flat=True)[:2]
            )
            if len(day_ids) != 1:
                summary["skipped"] += 1
                results.append(
                    {
                        "source_record_id": record.source_record_id,
                        "status": "skipped",
                    }
                )
                continue
            existing_exercise_day_id = (
                ActivityImport.objects.using(using)
                .filter(
                    user_id=device.user_id,
                    source=ActivityImport.SOURCE_GARMIN_HEALTH_CONNECT,
                    source_record_id=record.source_record_id,
                    exercise__day__plan__user_id=device.user_id,
                )
                .values_list("exercise__day_id", flat=True)
                .first()
            )
            lock_day_ids = set(day_ids)
            if existing_exercise_day_id is not None:
                lock_day_ids.add(existing_exercise_day_id)
            aggregate_locks = lock_plan_aggregate_rows(
                using=using, day_ids=lock_day_ids
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
                    {
                        "source_record_id": record.source_record_id,
                        "status": "skipped",
                    }
                )
                continue
            try:
                import_row = (
                    ActivityImport.objects.select_for_update()
                    .using(using)
                    .filter(
                        user_id=device.user_id,
                        source=ActivityImport.SOURCE_GARMIN_HEALTH_CONNECT,
                        source_record_id=record.source_record_id,
                    )
                    .first()
                )
                if import_row is not None and not import_row.is_active:
                    summary["unchanged"] += 1
                    results.append(
                        {
                            "source_record_id": record.source_record_id,
                            "status": "unchanged",
                        }
                    )
                    continue
                if (
                    import_row is not None
                    and record.source_modified_at
                    <= import_row.source_modified_at
                ):
                    summary["unchanged"] += 1
                    results.append(
                        {
                            "source_record_id": record.source_record_id,
                            "status": "unchanged",
                        }
                    )
                    continue

                exercise = None
                if (
                    import_row is not None
                    and import_row.exercise_id is not None
                ):
                    exercise = (
                        Exercise.objects.select_for_update()
                        .using(using)
                        .filter(
                            pk=import_row.exercise_id,
                            day__plan__user_id=device.user_id,
                        )
                        .first()
                    )
                replacing_existing = exercise is not None
                if exercise is not None and exercise.day_id != day.pk:
                    exercise.day = aggregate_locks.days_by_pk[exercise.day_id]
                    exercise.delete(using=using)
                    exercise = None

                if exercise is None:
                    exercise = Exercise.objects.using(using).create(
                        day=day,
                        time=record.time,
                        type=record.exercise_type,
                        kcals=record.active_kcals,
                        duration=record.duration,
                        distance=record.distance,
                    )
                    if import_row is None:
                        ActivityImport.objects.using(using).create(
                            exercise=exercise,
                            user_id=device.user_id,
                            device=device,
                            source=(
                                ActivityImport.SOURCE_GARMIN_HEALTH_CONNECT
                            ),
                            source_record_id=record.source_record_id,
                            source_modified_at=record.source_modified_at,
                            is_active=True,
                        )
                    else:
                        _save_import(
                            import_row,
                            using=using,
                            device=device,
                            record=record,
                            exercise=exercise,
                        )
                    status = "updated" if replacing_existing else "created"
                elif _exercise_matches(exercise, record):
                    _save_import(
                        cast(ActivityImport, import_row),
                        using=using,
                        device=device,
                        record=record,
                    )
                    status = "unchanged"
                else:
                    exercise.time = record.time
                    exercise.type = record.exercise_type
                    exercise.kcals = record.active_kcals
                    exercise.duration = record.duration
                    exercise.distance = record.distance
                    exercise.save(
                        using=using,
                        update_fields=[
                            "time",
                            "type",
                            "kcals",
                            "duration",
                            "distance",
                            "updated_at",
                        ],
                    )
                    _save_import(
                        cast(ActivityImport, import_row),
                        using=using,
                        device=device,
                        record=record,
                    )
                    status = "updated"

                summary[status] += 1
                results.append(
                    {
                        "source_record_id": record.source_record_id,
                        "status": status,
                    }
                )
            finally:
                aggregate_locks.clear_markers()

    return {"summary": summary, "records": results}


# pylint: enable=too-many-branches,too-many-statements


def update_manual_exercise(
    user: Any,
    exercise_id: int,
    *,
    exercise_type: str,
    kcals: int,
    time: datetime.time,
    duration: datetime.timedelta | None,
    distance: Decimal | None,
) -> Exercise:
    """Update an exercise and deactivate its import provenance under locks."""
    using = router.db_for_write(Exercise)
    day_id = (
        Exercise.objects.using(using)
        .filter(pk=exercise_id, day__plan__user=user)
        .values_list("day_id", flat=True)
        .first()
    )
    if day_id is None:
        raise ValueError("Exercise not found")
    with transaction.atomic(using=using):
        lock_plan_owner(using=using, user_id=user.pk)
        locks = lock_plan_aggregate_rows(using=using, day_ids=(day_id,))
        day = locks.days_by_pk.get(day_id)
        try:
            if day is None:
                raise ValueError("Exercise not found")
            try:
                exercise = (
                    Exercise.objects.select_for_update()
                    .using(using)
                    .get(pk=exercise_id, day=day)
                )
            except Exercise.DoesNotExist as exc:
                raise ValueError("Exercise not found") from exc
            exercise.time = time
            exercise.type = exercise_type
            exercise.kcals = kcals
            exercise.duration = duration
            exercise.distance = distance
            exercise.save(
                using=using,
                update_fields=[
                    "time",
                    "type",
                    "kcals",
                    "duration",
                    "distance",
                    "updated_at",
                ],
            )
            ActivityImport.objects.using(using).filter(
                exercise=exercise
            ).update(is_active=False, updated_at=timezone.now())
            return exercise
        finally:
            locks.clear_markers()


def delete_manual_exercise(user: Any, exercise_id: int) -> None:
    """Delete an exercise and detach its import provenance under locks."""
    using = router.db_for_write(Exercise)
    day_id = (
        Exercise.objects.using(using)
        .filter(pk=exercise_id, day__plan__user=user)
        .values_list("day_id", flat=True)
        .first()
    )
    if day_id is None:
        raise ValueError("Exercise not found")
    with transaction.atomic(using=using):
        lock_plan_owner(using=using, user_id=user.pk)
        locks = lock_plan_aggregate_rows(using=using, day_ids=(day_id,))
        day = locks.days_by_pk.get(day_id)
        try:
            if day is None:
                raise ValueError("Exercise not found")
            try:
                exercise = (
                    Exercise.objects.select_for_update()
                    .using(using)
                    .get(pk=exercise_id, day=day)
                )
            except Exercise.DoesNotExist as exc:
                raise ValueError("Exercise not found") from exc
            ActivityImport.objects.using(using).filter(
                exercise=exercise
            ).update(
                is_active=False,
                exercise=None,
                updated_at=timezone.now(),
            )
            exercise.delete(using=using)
        finally:
            locks.clear_markers()
