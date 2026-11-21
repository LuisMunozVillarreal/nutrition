"""Shared activity fixtures for real admin and calendar deletion tests."""

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.health_sync.models import HealthSyncDevice
from tests.health_sync.test_activity_api import _record, _upload


@pytest.fixture
def imported_activity(client, user_factory, day_factory):
    """Import a real activity belonging to someone other than the admin."""
    cache.clear()
    user = user_factory()
    day = day_factory(plan__user=user, day=timezone.localdate())
    token, _device = HealthSyncDevice.issue(user, "Phone")
    record = _record()
    assert _upload(client, token, record).json()["summary"]["created"] == 1
    exercise = Exercise.objects.get(day=day)
    yield exercise, token, record
    cache.clear()
