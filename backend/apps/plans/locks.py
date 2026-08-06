"""Canonical row locking for plan aggregate mutations."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, cast

from django.contrib.auth import get_user_model

if TYPE_CHECKING:
    from apps.plans.models import Day, WeekPlan


@dataclass
class GarminSyncUserLock:
    """Canonical row lock for Garmin user-level serialization."""

    using: str
    user: object


@dataclass
class PlanAggregateLocks:
    """Plan and day rows held in the canonical aggregate lock order."""

    using: str
    plans: tuple["WeekPlan", ...]
    days: tuple["Day", ...]

    @property
    def plans_by_pk(self) -> dict[int, "WeekPlan"]:
        """Return locked plans indexed by primary key.

        Returns:
            dict[int, WeekPlan]: Locked plans keyed by primary key.
        """
        return {plan.pk: plan for plan in self.plans}

    @property
    def days_by_pk(self) -> dict[int, "Day"]:
        """Return locked days indexed by primary key.

        Returns:
            dict[int, Day]: Locked days keyed by primary key.
        """
        return {day.pk: day for day in self.days}

    def covers_days(self, day_ids: Iterable[int], using: str) -> bool:
        """Return whether these live locks cover all requested days.

        Args:
            day_ids (Iterable[int]): Day primary keys that must be covered.
            using (str): Database alias on which locks are held.

        Returns:
            bool: Whether all requested days are covered on the same database.
        """
        return self.using == using and set(day_ids).issubset(self.days_by_pk)

    def covers_plans(self, plan_ids: Iterable[int], using: str) -> bool:
        """Return whether these live locks cover all requested plans.

        Args:
            plan_ids (Iterable[int]): Plan primary keys that must be covered.
            using (str): Database alias on which locks are held.

        Returns:
            bool: Whether all requested plans are covered on the same database.
        """
        return self.using == using and set(plan_ids).issubset(self.plans_by_pk)

    def clear_markers(self) -> None:
        """Remove transaction-scoped lock markers from returned model objects."""
        for day in self.days:
            if getattr(day, "_plan_aggregate_locks", None) is self:
                setattr(day, "_plan_aggregate_locks", None)

    def recompute_days(
        self,
        day_ids: Iterable[int],
        *,
        using: str,
    ) -> None:
        """Recompute all locked day rows by primary key."""
        if self.using != using:
            return
        for day_id in sorted(day_ids):
            day = self.days_by_pk.get(day_id)
            if day is not None:
                day.save(using=using)


def lock_plan_aggregate_rows(
    *,
    using: str,
    day_ids: Iterable[int] = (),
    plan_ids: Iterable[int] = (),
) -> PlanAggregateLocks:
    """Lock plans by PK, then their affected days by PK.

    All code that updates state derived across ``WeekPlan`` and ``Day`` rows
    must use this order. Resolving each day's parent is intentionally a plain
    read before either lock class is acquired; the parent relation is immutable
    for supported plan operations.

    Args:
        using (str): Database alias on which to acquire locks.
        day_ids (Iterable[int]): Affected day primary keys.
        plan_ids (Iterable[int]): Additional affected plan primary keys.

    Returns:
        PlanAggregateLocks: Locked plans and days in deterministic order.
    """
    from apps.plans.models.day import Day
    from apps.plans.models.week import WeekPlan

    day_manager = cast(Any, Day).objects
    plan_manager = cast(Any, WeekPlan).objects

    normalized_day_ids = tuple(sorted(set(day_ids)))
    normalized_plan_ids = set(plan_ids)
    if normalized_day_ids:
        normalized_plan_ids.update(
            Day.objects.using(using)
            .filter(pk__in=normalized_day_ids)
            .values_list("plan_id", flat=True)
        )

    plans = tuple(
        plan
        for plan in plan_manager.select_for_update(of=("self",))
        .using(using)
        .filter(pk__in=normalized_plan_ids)
        .order_by("pk")
    )
    plans_by_pk = {plan.pk: plan for plan in plans}
    days = tuple(
        day
        for day in day_manager.select_for_update(of=("self",))
        .using(using)
        .filter(pk__in=normalized_day_ids)
        .order_by("pk")
    )
    for day in days:
        day.plan = plans_by_pk[day.plan_id]
    locks = PlanAggregateLocks(using=using, plans=plans, days=days)
    for day in days:
        setattr(day, "_plan_aggregate_locks", locks)
    return locks


def lock_user_for_garmin_sync(
    *, using: str, user_id: int
) -> GarminSyncUserLock:
    """Return a row-level lock for one user during Garmin synchronization."""
    user_model = get_user_model()
    user = (
        user_model.objects.select_for_update(of=("self",))
        .using(using)
        .get(pk=user_id)
    )
    return GarminSyncUserLock(using=using, user=user)
