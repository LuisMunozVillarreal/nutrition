"""Garmin sync logic."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from django.utils import timezone

from apps.exercises.models import Exercise
from apps.plans.models.week import WeekPlan
from apps.users.models import User

from .models import GarminActivity, GarminCredential
from .service import GarminService

logger = logging.getLogger(__name__)


def sync_activities(user: User) -> None:
    """Sync Garmin activities for a user.

    Args:
        user (User): user instance.
    """
    # pylint: disable=too-many-locals
    try:
        cred = user.garmin_credential
    except GarminCredential.DoesNotExist:
        logger.info("User %s has no Garmin credentials.", user)
        return

    service = GarminService()
    # Fetch last 7 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=7)

    try:
        activities: List[Dict[str, Any]] = service.fetch_activities(
            cred.access_token, start_date, end_date
        )
    # pylint: disable=broad-exception-caught
    except Exception as e:
        logger.error("Failed to fetch activities for %s: %s", user, e)
        return

    for activity in activities:
        # Check if already synced
        activity_id_raw = activity.get("activityId")
        if not activity_id_raw:
            continue
        activity_id = str(activity_id_raw)

        if GarminActivity.objects.filter(
            garmin_activity_id=activity_id
        ).exists():
            continue

        # Filter for cycling
        activity_type = activity.get("activityType", {}).get(
            "typeKey"
        ) or activity.get("type")

        if activity_type != "cycling":
            continue

        # Parse date and time
        try:
            start_time_local = datetime.strptime(
                activity["startTimeLocal"], "%Y-%m-%d %H:%M:%S"
            )
        except (ValueError, KeyError):
            continue

        activity_date = start_time_local.date()
        activity_time = start_time_local.time()

        # Find or Create Day
        # improved logic: find week plan first
        plan = (
            WeekPlan.objects.filter(
                user=user,
                start_date__lte=activity_date,
            )
            .order_by("-start_date")
            .first()
        )

        if not plan:
            logger.debug(
                "No active plan found for %s on %s", user, activity_date
            )
            continue

        # Calculate day number. Assuming weekly plans start on start_date
        # Logic depends on how WeekPlan works.
        # Looking at WeekPlan model, it has 'days'.
        # We can try to get the day from the plan.

        # Simply get_or_create from plan.days
        # But we need to know which 'day_num' it is if we create it?
        # Let's see if the day exists first.
        day = plan.days.filter(day=activity_date).first()

        if not day:
            # We need to rely on the plan logic to create days usually.
            # If the day doesn't exist, it might mean the plan initialization
            # didn't create it or it's out of range of the 7 days?
            # WeekPlan.PLAN_LENGTH_DAYS = 7
            delta = (activity_date - plan.start_date).days
            if 0 <= delta < 7:
                # It should exist if plan was initialized correctly.
                # If not, let's skip or try to create?
                # Safest is to skip if not found, to avoid messing up plan
                # logic
                logger.warning("Day not found in plan for %s", activity_date)
                continue

            # Activity date outside plan range (even if plan started before
            # )
            continue

        # Create Exercise
        try:
            exercise = Exercise.objects.create(
                day=day,
                time=activity_time,
                type=Exercise.EXERCISE_CYCLE,
                kcals=activity.get("calories", 0),
                duration=timedelta(seconds=activity.get("duration", 0)),
                distance=activity.get("distance", 0) / 1000,  # meters to km
            )

            # Track sync
            GarminActivity.objects.create(
                exercise=exercise,
                garmin_activity_id=activity_id,
                data=activity,
            )

            logger.info(
                "Synced cycling activity %s for %s on %s",
                activity_id,
                user,
                activity_date,
            )
        # pylint: disable=broad-exception-caught
        except Exception as e:
            logger.error("Failed to create exercise: %s", e)
