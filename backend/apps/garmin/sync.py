"""Garmin sync logic."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from django.utils import timezone

from apps.exercises.models import Exercise
from apps.plans.models.day import Day
from apps.users.models import User

from .models import GarminCredential
from .service import GarminService

logger = logging.getLogger(__name__)


def sync_activities(user: User) -> None:
    """Sync Garmin activities for a user.

    Args:
        user (User): user instance.
    """
    try:
        cred = user.garmin_credential
    except GarminCredential.DoesNotExist:
        logger.info("User %s has no Garmin credentials.", user)
        return

    service = GarminService()
    # Fetch last 7 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=7)

    # Note: Token refresh logic should be here or in service.
    # For now assuming valid token or relying on service to handle/fail.

    try:
        activities: List[Dict[str, Any]] = service.fetch_activities(
            cred.access_token, start_date, end_date
        )
    # pylint: disable=broad-exception-caught
    except Exception as e:
        logger.error("Failed to fetch activities for %s: %s", user, e)
        return

    for activity in activities:
        # Filter for cycling (and potentially others in future)
        # Garmin API returns 'typeKey' in 'activityType'.
        # For simplicity in this mock/stub, we assume 'type' field.
        activity_type = activity.get("activityType", {}).get(
            "typeKey"
        ) or activity.get("type")

        if activity_type != "cycling":
            continue

        # Parse date and time
        # Garmin standard: startTimeLocal "2010-01-01 10:00:00"
        try:
            start_time_local = datetime.strptime(
                activity["startTimeLocal"], "%Y-%m-%d %H:%M:%S"
            )
        except (ValueError, KeyError):
            continue

        activity_date = start_time_local.date()
        activity_time = start_time_local.time()

        # Find Day
        day = Day.objects.filter(plan__user=user, day=activity_date).first()
        if not day:
            logger.debug("No plan day found for %s on %s", user, activity_date)
            continue

        # Check for duplicates
        # Using type and time as unique-ish constraint
        exists = Exercise.objects.filter(
            day=day,
            type=Exercise.EXERCISE_CYCLE,
            time=activity_time,
        ).exists()

        if exists:
            continue

        # Create Exercise
        try:
            Exercise.objects.create(
                day=day,
                time=activity_time,
                type=Exercise.EXERCISE_CYCLE,
                kcals=activity.get("calories", 0),
                duration=timedelta(seconds=activity.get("duration", 0)),
                distance=activity.get("distance", 0) / 1000,  # meters to km
            )
            logger.info(
                "Synced cycling activity for %s on %s", user, activity_date
            )
        # pylint: disable=broad-exception-caught
        except Exception as e:
            logger.error("Failed to create exercise: %s", e)
