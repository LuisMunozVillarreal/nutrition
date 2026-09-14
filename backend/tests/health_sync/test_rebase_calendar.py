"""Calendar integration regressions for manual Health Sync totals."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.exercises import schema as exercise_schema
from apps.health_sync.services import create_manual_day_steps
from apps.plans import locks
from config.schema import schema

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("selector", ["dayId", "dayDate"])
def test_manual_steps_lock_owner_before_calendar_resolution(
    week_plan, selector
):
    """Calendar locks must not precede the owner lock used by device sync."""
    day = week_plan.days.get(day_num=1)
    value = str(day.pk) if selector == "dayId" else f'"{day.day.isoformat()}"'
    original = exercise_schema.resolve_day
    with patch(
        "apps.plans.locks.lock_plan_owner", wraps=locks.lock_plan_owner
    ) as owner_lock:

        def resolve_after_owner(*args, **kwargs):
            """Resolve the real calendar only after the owner is locked."""
            assert owner_lock.called, "calendar resolution preceded owner lock"
            return original(*args, **kwargs)

        with patch(
            "apps.exercises.schema.resolve_day",
            side_effect=resolve_after_owner,
        ):
            result = schema.execute_sync(
                f"mutation {{ createDaySteps({selector}: {value}, steps: 100) "
                "{ id } }",
                context_value=SimpleNamespace(
                    request=SimpleNamespace(user=week_plan.user)
                ),
            )
    assert result.errors is None
    assert day.steps.steps == 100


def test_manual_service_rejects_missing_owned_day(user):
    """The service itself keeps its missing-day guard beyond the API resolver."""
    with pytest.raises(ValueError, match="Day not found"):
        create_manual_day_steps(user, 999999, 100)
