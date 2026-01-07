from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.exercises.models import Exercise
from apps.garmin.models import GarminActivity, GarminCredential
from apps.garmin.sync import sync_activities
from apps.plans.models.day import Day
from apps.plans.models.week import WeekPlan
from apps.users.models import User


@pytest.mark.django_db
class TestGarminSync:
    """Test Garmin sync logic."""

    @pytest.fixture
    def user(self):
        """Create user."""
        return User.objects.create_user(
            email="test@example.com",
            password="password",
            date_of_birth=datetime(1990, 1, 1).date(),
            height=180,
        )

    @pytest.fixture
    def measurement(self, user):
        from apps.measurements.models import Measurement

        return Measurement.objects.create(
            user=user, weight=80, body_fat_perc=20
        )

    @pytest.fixture
    def plan(self, user, measurement):
        """Create week plan."""
        start_date = datetime.now().date() - timedelta(days=1)
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=start_date,
            protein_g_kg=Decimal("2.0"),
            fat_perc=Decimal("25.0"),
            deficit=0,
        )
        # Create days
        for i in range(7):
            Day.objects.create(
                plan=plan,
                day=start_date + timedelta(days=i),
                day_num=i + 1,
                energy_kcal_goal=2000,
                protein_g_goal=150,
                fat_g_goal=60,
                carbs_g_goal=200,
            )
        return plan

    @pytest.fixture
    def credential(self, user):
        """Create garmin credential."""
        return GarminCredential.objects.create(
            user=user,
            access_token="token",
            refresh_token="refresh",
            expires_at=1234567890,
            garmin_user_id="12345",
        )

    @patch("apps.garmin.sync.GarminService")
    def test_sync_activities(self, MockService, user, plan, credential):
        """Test sync activities."""
        # Mock service
        service = MockService.return_value

        # Activity data
        activity_date = datetime.now().date()
        start_time_local = datetime.combine(
            activity_date, datetime.now().time()
        ).strftime("%Y-%m-%d %H:%M:%S")

        service.fetch_activities.return_value = [
            {
                "activityId": "987654",
                "activityName": "Test Ride",
                "startTimeLocal": start_time_local,
                "type": "cycling",
                "distance": 10000.0,
                "duration": 1800.0,
                "calories": 300,
            }
        ]

        # Sync
        sync_activities(user)

        # Verify
        assert Exercise.objects.count() == 1
        exercise = Exercise.objects.first()
        assert exercise.type == Exercise.EXERCISE_CYCLE
        assert exercise.kcals == 300

        assert GarminActivity.objects.count() == 1
        ga = GarminActivity.objects.first()
        assert ga.garmin_activity_id == "987654"
        assert ga.exercise == exercise

        # Sync again (deduplication)
        sync_activities(user)
        assert Exercise.objects.count() == 1
        assert GarminActivity.objects.count() == 1
