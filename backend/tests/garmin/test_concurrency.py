"""PostgreSQL concurrency regressions for Garmin activity imports."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import close_old_connections, connection, router, transaction
from django.test import TransactionTestCase
from django.utils import timezone

import apps.garmin.services as services
from apps.garmin.models import GarminActivity, GarminConnection
from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan

from . import test_services


@skipUnless(
    connection.vendor == "postgresql"
    and connection.features.has_select_for_update,
    "PostgreSQL row locks are required",
)
class GarminSyncConcurrencyTests(TransactionTestCase):
    """PostgreSQL-specific Garmin lock-order and batch safety regressions."""

    reset_sequences = True
    serialized_rollback = True

    @classmethod
    def setUpClass(cls):
        """Configure provider settings shared by concurrency tests."""
        super().setUpClass()
        cls._garmin_settings = {
            "GARMIN_ENABLED": True,
            "GARMIN_CLIENT_ID": "garmin-client-id",
            "GARMIN_CLIENT_SECRET": "garmin-secret",
            "GARMIN_AUTHORIZATION_URL": "https://garmin.example.com/auth",
            "GARMIN_TOKEN_URL": "https://garmin.example.com/token",
            "GARMIN_ACTIVITIES_URL": "https://garmin.example.com/activities",
            "GARMIN_CALLBACK_URL": "https://app.example.com/callback",
            "GARMIN_SCOPES": "read write",
            "GARMIN_PROVIDER_ORIGINS": ["https://garmin.example.com"],
            "GARMIN_CALLBACK_ALLOWED_ORIGINS": ["https://app.example.com"],
            "GARMIN_REQUEST_TIMEOUT_SECONDS": 10,
            "GARMIN_ACTIVITY_MAX_PAGES": 3,
            "GARMIN_ACTIVITY_SYNC_BATCH_SIZE": 1,
            "GARMIN_ACTIVITIES_LIMIT": 100,
            "GARMIN_STATE_TTL_SECONDS": 300,
            "GARMIN_STATE_MAX_IN_FLIGHT": 2,
            "GARMIN_TOKEN_MAX_TTL_SECONDS": 3600,
            "GARMIN_ACTIVITY_ENDPOINT_MAX_RESPONSE_BYTES": 1024 * 1024,
            "GARMIN_TOKEN_ENDPOINT_MAX_RESPONSE_BYTES": 512 * 1024,
            "GARMIN_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }

    @classmethod
    def setUpTestData(cls):
        """Create a user-owned day for concurrent imports."""
        cls.user = test_services._create_user("garmin-concurrency@example.com")
        measurement = Measurement.objects.create(
            user=cls.user,
            weight=Decimal("80.0"),
            body_fat_perc=Decimal("20.0"),
        )
        plan = WeekPlan.objects.create(
            user=cls.user,
            measurement=measurement,
            start_date=date.today(),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25.0"),
            deficit=500,
        )
        day = Day.objects.filter(plan=plan).first()
        assert day is not None
        cls.day = day

    def setUp(self):
        """Apply isolated Garmin settings before each test."""
        super().setUp()
        self._previous_settings: dict[str, object] = {}
        for key, value in self._garmin_settings.items():
            self._previous_settings[key] = getattr(settings, key, None)
            setattr(settings, key, value)

    def tearDown(self):
        """Restore settings and close the test fixture."""
        for key, previous in self._previous_settings.items():
            setattr(settings, key, previous)
        self._previous_settings.clear()
        super().tearDown()

    @staticmethod
    def _run_workers(*workers):
        outcomes = []
        ready = threading.Barrier(len(workers))

        def run(worker):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                summary = worker()
            finally:
                close_old_connections()
            outcomes.append(summary)

        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            for future in [executor.submit(run, worker) for worker in workers]:
                future.result(timeout=20)

        return outcomes

    @staticmethod
    def _create_payload_for_day(day: Day, *, activity_id: str):
        return [
            test_services._activity_payload(
                activity_id=activity_id,
                activity_type="cycle",
                started_at=day.day.isoformat(),
            )
        ]

    def _create_connection(self):
        connection = GarminConnection.objects.create(user=self.user)
        connection.set_tokens(
            services.GarminTokenPair(
                access_token="access-token",
                refresh_token="refresh-token",
                expires_in=3600,
                scope="read",
                provider_account_id="provider-user",
            ),
            expires_in=3600,
        )
        connection.save(
            update_fields=[
                "access_token_encrypted",
                "refresh_token_encrypted",
                "access_token_expires_at",
                "provider_scopes",
                "provider_account_id",
                "status",
                "connection_generation",
                "updated_at",
            ]
        )
        return connection

    def test_concurrent_syncs_do_not_create_duplicate_rows(self):
        """Concurrent sync operations should converge to one imported row."""
        connection = self._create_connection()
        payload = self._create_payload_for_day(
            self.day, activity_id="shared-1"
        )

        with patch.object(
            services,
            "_iter_activity_payloads",
            lambda *_, **__: payload,
        ):
            outcomes = self._run_workers(
                lambda: services.sync_connection(
                    GarminConnection.objects.get(pk=connection.pk)
                ),
                lambda: services.sync_connection(
                    GarminConnection.objects.get(pk=connection.pk)
                ),
            )

        assert len(outcomes) == 2
        assert {summary.imported for summary in outcomes} == {0, 1}
        assert {summary.duplicates for summary in outcomes} == {0, 1}
        assert (
            GarminActivity.objects.filter(
                connection=connection,
                provider_activity_id="shared-1",
            ).count()
            == 1
        )

    def test_sync_connection_rejects_state_change_between_batches(self):
        """Abort sync when the connection changes mid-batch."""
        connection = self._create_connection()
        payloads = [
            test_services._activity_payload(
                activity_id="batch-1",
                activity_type="cycle",
                started_at=self.day.day.isoformat(),
            ),
            test_services._activity_payload(
                activity_id="batch-2",
                activity_type="cycle",
                started_at=self.day.day.isoformat(),
            ),
        ]

        using = router.db_for_write(services.GarminActivity)
        original_ensure = services._ensure_exercise
        state = {"mutated": False}

        def _ensure_with_state_bump(*args, **kwargs):
            if not state["mutated"]:
                state["mutated"] = True
                with transaction.atomic(using=using):
                    active_connection = (
                        GarminConnection.objects.using(using)
                        .select_for_update(of=("self",))
                        .get(pk=connection.pk)
                    )
                    active_connection.connection_generation += 1
                    active_connection.status = (
                        services.GarminConnection.Status.DISCONNECTED
                    )
                    active_connection.save(
                        using=using,
                        update_fields=["connection_generation", "status"],
                    )
            return original_ensure(*args, **kwargs)

        with (
            patch.object(
                services,
                "_iter_activity_payloads",
                lambda *_, **__: payloads,
            ),
            patch.object(
                services, "_ensure_exercise", _ensure_with_state_bump
            ),
        ):
            with pytest.raises(
                ValueError,
                match="Garmin connection state changed during sync",
            ):
                services.sync_connection(connection)

        assert (
            GarminActivity.objects.filter(
                connection=connection,
                provider_activity_id="batch-1",
            ).count()
            == 1
        )
        assert (
            GarminActivity.objects.filter(
                connection=connection,
                provider_activity_id="batch-2",
            ).count()
            == 0
        )

    def test_sync_connection_concurrent_with_exercise_update_is_idempotent(
        self,
    ):
        """Concurrent manual exercise updates should not deadlock."""
        connection = self._create_connection()
        started_at = timezone.make_aware(
            datetime.combine(self.day.day, time(9, 0))
        )
        original_exercise = services.Exercise.objects.create(
            day=self.day,
            time=time(9, 0),
            type=services.Exercise.EXERCISE_CYCLE,
            kcals=111,
            duration=timedelta(minutes=20),
            distance=Decimal("1.00"),
        )
        GarminActivity.objects.create(
            connection=connection,
            provider_activity_id="manual-update-1",
            provider_activity_type="cycle",
            provider_account_id="provider-user",
            day=self.day,
            exercise=original_exercise,
            provider_local_started_date=self.day.day,
            provider_local_started_time=time(9, 0),
            provider_timezone_offset_minutes=0,
            started_at=started_at,
            kcals=111,
            duration_seconds=1200,
            distance=Decimal("1.00"),
        )

        payloads = [
            test_services._activity_payload(
                activity_id="manual-update-1",
                activity_type="cycle",
                started_at=started_at.isoformat(),
            )
        ]

        def _manual_update() -> None:
            exercise = services.Exercise.objects.get(pk=original_exercise.pk)
            exercise.kcals = 222
            exercise.save()

        with patch.object(
            services,
            "_iter_activity_payloads",
            lambda *_, **__: payloads,
        ):
            outcomes = self._run_workers(
                lambda: services.sync_connection(
                    GarminConnection.objects.get(pk=connection.pk)
                ),
                _manual_update,
            )

        assert len(outcomes) == 2
        assert (
            GarminActivity.objects.filter(
                connection=connection,
                provider_activity_id="manual-update-1",
            ).count()
            == 1
        )

    def test_sync_connection_concurrent_with_exercise_delete_is_idempotent(
        self,
    ):
        """Concurrent delete and sync should remain consistent."""
        connection = self._create_connection()
        started_at = timezone.make_aware(
            datetime.combine(self.day.day, time(9, 0))
        )
        original_exercise = services.Exercise.objects.create(
            day=self.day,
            time=time(9, 0),
            type=services.Exercise.EXERCISE_CYCLE,
            kcals=111,
            duration=timedelta(minutes=20),
            distance=Decimal("1.00"),
        )
        GarminActivity.objects.create(
            connection=connection,
            provider_activity_id="manual-delete-1",
            provider_activity_type="cycle",
            provider_account_id="provider-user",
            day=self.day,
            exercise=original_exercise,
            provider_local_started_date=self.day.day,
            provider_local_started_time=time(9, 0),
            provider_timezone_offset_minutes=0,
            started_at=started_at,
            kcals=111,
            duration_seconds=1200,
            distance=Decimal("1.00"),
        )

        payloads = [
            test_services._activity_payload(
                activity_id="manual-delete-1",
                activity_type="cycle",
                started_at=started_at.isoformat(),
            )
        ]

        with patch.object(
            services,
            "_iter_activity_payloads",
            lambda *_, **__: payloads,
        ):
            outcomes = self._run_workers(
                lambda: services.sync_connection(
                    GarminConnection.objects.get(pk=connection.pk)
                ),
                lambda: services.Exercise.objects.get(
                    pk=original_exercise.pk
                ).delete(),
            )

        assert len(outcomes) == 2
        assert (
            GarminActivity.objects.filter(
                connection=connection,
                provider_activity_id="manual-delete-1",
            ).count()
            == 1
        )
