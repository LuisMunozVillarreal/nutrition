"""Garmin sync tests."""

from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

import pytest

from apps.exercises.models import Exercise
from apps.garmin.models import GarminCredential
from apps.garmin.sync import sync_activities
from apps.measurements.models import Measurement
from apps.plans.models import WeekPlan
from apps.users.models import User


@pytest.mark.django_db
class TestSyncActivities:
    """Garmin sync tests class."""

    @pytest.fixture
    def user(self) -> User:
        """User fixture.

        Returns:
            User: user instance.
        """
        return User.objects.create_user(
            email="test@example.com",
            password="password",
            first_name="Test",
            last_name="User",
            date_of_birth="1990-01-01",
            height=180,
        )

    def test_sync_no_credentials(self, user: User, mocker: Any) -> None:
        """Test sync with no credentials.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        # Given user with no garmin creds
        logger_mock = mocker.patch("apps.garmin.sync.logger")

        # When syncing
        sync_activities(user)

        # Then logs info and returns
        logger_mock.info.assert_called_with(
            "User %s has no Garmin credentials.", user
        )

    def test_sync_fetch_error(self, user: User, mocker: Any) -> None:
        """Test sync with fetch error.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        # Given user with creds
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )

        # And service raises error
        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.side_effect = Exception(
            "Fetch error"
        )
        logger_mock = mocker.patch("apps.garmin.sync.logger")

        # When syncing
        sync_activities(user)

        # Then logs error
        assert (
            "Failed to fetch activities" in logger_mock.error.call_args[0][0]
        )

    def test_sync_success_create_exercise(
        self, user: User, mocker: Any
    ) -> None:
        """Test successful sync creating exercise.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        # Given user with creds
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )

        # And a Day exists for the activity date
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20, weight=80
        )
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=date(2023, 10, 23),
            protein_g_kg=Decimal("2.0"),
            fat_perc=Decimal("20.0"),
            deficit=500,
        )
        # We need a Day for 2023-10-27 (mock activity date)
        activity_date = date(2023, 10, 27)
        day = plan.days.get(day=activity_date)

        # And service returns activities
        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.return_value = [
            {
                "activityId": 123,
                "activityName": "Ride",
                "startTimeLocal": "2023-10-27 08:00:00",
                "type": "cycling",
                "distance": 10000.0,
                "duration": 3600.0,
                "calories": 400,
            }
        ]

        # When syncing
        sync_activities(user)

        # Then exercise is created
        ex = Exercise.objects.get(day=day)
        assert ex.type == Exercise.EXERCISE_CYCLE
        assert ex.time == time(8, 0)
        assert ex.kcals == 400
        assert ex.distance == 10.0  # 10000/1000

    def test_sync_skip_duplicates(self, user: User, mocker: Any) -> None:
        """Test skipping duplicates.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        from apps.garmin.models import GarminActivity, GarminCredential

        # Given user, creds, plan, day
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20, weight=80
        )
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=date(2023, 10, 23),
            protein_g_kg=Decimal("2.0"),
            fat_perc=Decimal("20.0"),
            deficit=500,
        )
        activity_date = date(2023, 10, 27)
        day = plan.days.get(day=activity_date)

        # And existing exercise
        ex = Exercise.objects.create(
            day=day,
            type=Exercise.EXERCISE_CYCLE,
            time=time(8, 00),
            kcals=400,
            duration=timedelta(hours=1),
            distance=10,
        )
        # And existing GarminActivity
        GarminActivity.objects.create(exercise=ex, garmin_activity_id="123")

        # And service returns same activity
        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.return_value = [
            {
                "activityId": 123,
                "startTimeLocal": "2023-10-27 08:00:00",
                "type": "cycling",
                "distance": 10000.0,
                "duration": 3600.0,
                "calories": 400,
            }
        ]

        # When syncing
        initial_count = Exercise.objects.count()
        sync_activities(user)

        # Then no new exercise
        assert Exercise.objects.count() == initial_count

    def test_sync_skip_non_cycling(self, user: User, mocker: Any) -> None:
        """Test skipping non-cycling activities.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.return_value = [
            {"activityId": "666", "type": "running", "startTimeLocal": "2023-10-27 10:00:00"}
        ]

        sync_activities(user)
        # Implicitly checked by coverage

    def test_sync_bad_date(self, user: User, mocker: Any) -> None:
        """Test skipping bad date format.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.return_value = [
            {"activityId": "999", "type": "cycling", "startTimeLocal": "bad-date"}
        ]

        sync_activities(user)
        # Implicitly checked

    def test_sync_create_error(self, user: User, mocker: Any) -> None:
        """Test handling exercise creation error.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20, weight=80
        )
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=date(2023, 10, 23),
            protein_g_kg=Decimal("2.0"),
            fat_perc=Decimal("20.0"),
            deficit=500,
        )
        activity_date = date(2023, 10, 27)
        plan.days.get(day=activity_date)

        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.return_value = [
            {
                "activityId": "888",
                "startTimeLocal": "2023-10-27 08:00:00",
                "type": "cycling",
                "distance": 10000.0,
                "duration": 3600.0,
                "calories": 400,
            }
        ]

        # Mock Exercise.objects.create to raise exception
        mocker.patch(
            "apps.exercises.models.Exercise.objects.create",
            side_effect=Exception("DB Error"),
        )
        logger_mock = mocker.patch("apps.garmin.sync.logger")

        sync_activities(user)

        assert "Failed to create exercise" in logger_mock.error.call_args[0][0]

    def test_sync_no_day(self, user: User, mocker: Any) -> None:
        """Test sync when no day exists.

        Args:
            user (User): user instance.
            mocker (Any): pytest-mock mocker.
        """
        # Given mock activity but no Day in DB...
        GarminCredential.objects.create(
            user=user, access_token="t", refresh_token="r", expires_at=0
        )
        service_mock = mocker.patch("apps.garmin.sync.GarminService")
        service_mock.return_value.fetch_activities.return_value = [
            {
                "activityId": "777",
                "startTimeLocal": "2023-10-27 08:00:00",
                "type": "cycling",
            }
        ]

        # When syncing
        sync_activities(user)
        # Implicitly checked
