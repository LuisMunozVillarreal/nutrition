"""Test Garmin Sync v2."""

# pylint: disable=redefined-outer-name,unused-argument,duplicate-code

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from apps.exercises.models import Exercise
from apps.garmin.models import GarminActivity, GarminCredential
from apps.garmin.sync import sync_activities
from apps.plans.models.day import Day
from apps.plans.models.week import WeekPlan
from apps.users.models import User

if TYPE_CHECKING:
    from apps.measurements.models import Measurement


@pytest.mark.django_db
class TestGarminSync:
    """Test Garmin sync logic."""

    @pytest.fixture
    def user(self) -> User:
        """Create user.

        Returns:
            User: user instance.
        """
        return User.objects.create_user(
            email="test@example.com",
            password="password",
            date_of_birth=datetime(1990, 1, 1).date(),
            height=180,
        )

    @pytest.fixture
    def measurement(self, user: User) -> "Measurement":  # type: ignore
        """Create measurement.

        Args:
            user (User): user instance.

        Returns:
            Measurement: measurement instance.
        """
        from apps.measurements.models import Measurement

        return Measurement.objects.create(
            user=user, weight=80, body_fat_perc=20
        )

    @pytest.fixture
    def plan(
        self, user: User, measurement: "Measurement"  # type: ignore
    ) -> WeekPlan:
        """Create week plan.

        Args:
            user (User): user instance.
            measurement (Measurement): measurement instance.

        Returns:
            WeekPlan: week plan instance.
        """
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
    def credential(self, user: User) -> GarminCredential:
        """Create garmin credential.

        Args:
            user (User): user instance.

        Returns:
            GarminCredential: credential instance.
        """
        return GarminCredential.objects.create(
            user=user,
            access_token="token",
            refresh_token="refresh",
            expires_at=1234567890,
            garmin_user_id="12345",
        )

    @patch("apps.garmin.sync.GarminService")
    def test_sync_activities(
        self,
        mock_service: MagicMock,
        user: User,
        plan: WeekPlan,
        credential: GarminCredential,
    ) -> None:
        """Test sync activities.

        Args:
            mock_service (MagicMock): mocked service.
            user (User): user instance.
            plan (WeekPlan): plan instance.
            credential (GarminCredential): credential instance.
        """
        # Mock service
        service = mock_service.return_value

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

        # Test string representation for coverage
        assert str(credential) == f"Garmin Credential for {user}"
        assert str(ga) == "Garmin Activity 987654"

    @patch("apps.garmin.sync.GarminService")
    def test_sync_no_activity_id(
        self,
        mock_service: MagicMock,
        user: User,
        credential: GarminCredential,
    ) -> None:
        """Test sync ignores activity with no ID.

        Args:
            mock_service (MagicMock): mocked service.
            user (User): user instance.
            credential (GarminCredential): credential instance.
        """
        service = mock_service.return_value
        service.fetch_activities.return_value = [{"activityName": "No ID"}]
        sync_activities(user)
        assert Exercise.objects.count() == 0

    @patch("apps.garmin.sync.GarminService")
    def test_sync_missing_day(
        self,
        mock_service: MagicMock,
        user: User,
        plan: WeekPlan,
        credential: GarminCredential,
    ) -> None:
        """Test sync logic when Day is missing from Plan.

        Args:
            mock_service (MagicMock): mocked service.
            user (User): user instance.
            plan (WeekPlan): plan instance.
            credential (GarminCredential): credential instance.
        """
        # Delete day corresponding to today
        activity_date = datetime.now().date()
        Day.objects.filter(day=activity_date).delete()

        service = mock_service.return_value
        start_time_local = datetime.combine(
            activity_date, datetime.now().time()
        ).strftime("%Y-%m-%d %H:%M:%S")

        service.fetch_activities.return_value = [
            {
                "activityId": "111",
                "startTimeLocal": start_time_local,
                "type": "cycling",
            }
        ]

        # Should log warning but continue (not crash)
        sync_activities(user)
        assert Exercise.objects.count() == 0

    @patch("apps.garmin.sync.GarminService")
    def test_sync_outside_plan_range(
        self,
        mock_service: MagicMock,
        user: User,
        plan: WeekPlan,
        credential: GarminCredential,
    ) -> None:
        """Test sync when activity is outside plan range.

        Args:
            mock_service (MagicMock): mocked service.
            user (User): user instance.
            plan (WeekPlan): plan instance.
            credential (GarminCredential): credential instance.
        """
        # Activity is 8 days after plan start
        plan.start_date = datetime.now().date() - timedelta(days=10)
        plan.save()
        Day.objects.all().delete()  # Ensure no days exist

        activity_date = plan.start_date + timedelta(days=8)

        service = mock_service.return_value
        start_time_local = datetime.combine(
            activity_date, datetime.now().time()
        ).strftime("%Y-%m-%d %H:%M:%S")

        service.fetch_activities.return_value = [
            {
                "activityId": "222",
                "startTimeLocal": start_time_local,
                "type": "cycling",
            }
        ]

        sync_activities(user)
        assert Exercise.objects.count() == 0
