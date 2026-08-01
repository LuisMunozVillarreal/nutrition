"""PostgreSQL concurrency regressions for Garmin activity imports."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest import skipUnless
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

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
    """Garmin sync uses row locks.

    Avoids duplicate inserts under contention.
    """

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
            "GARMIN_REQUEST_TIMEOUT_SECONDS": 10,
            "GARMIN_ACTIVITY_MAX_PAGES": 3,
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
            weight=80.0,
            body_fat_perc=20.0,
        )
        plan = WeekPlan.objects.create(
            user=cls.user,
            measurement=measurement,
            start_date=date.today(),
            protein_g_kg=1.8,
            fat_perc=25.0,
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
        ready = threading.Barrier(len(workers))
        outcomes = []
        lock = threading.Lock()

        def run(worker):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                summary = worker()
            finally:
                close_old_connections()
            with lock:
                outcomes.append(summary)

        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            for future in [executor.submit(run, worker) for worker in workers]:
                future.result(timeout=20)

        return outcomes

    @staticmethod
    def _create_payload_for_day(day: Day):
        return [
            test_services._activity_payload(
                activity_id="shared-1",
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
        payload = self._create_payload_for_day(self.day)

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
