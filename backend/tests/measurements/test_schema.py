"""Tests for Measurements GraphQL schema."""

import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.measurements.models import Measurement
from apps.plans.models import Day, WeekPlan
from config.schema import schema

User = get_user_model()


@pytest.mark.django_db
class TestMeasurementsQuery:
    """Tests for measurement queries."""

    def test_measurements_unauthenticated(self):
        """Test measurements query without authentication."""
        # When querying measurements without auth
        query = "{ measurements { id } }"
        result = schema.execute_sync(query, context_value=None)

        # Then the result is an empty list
        assert result.data["measurements"] == []

    def test_measurements_returns_user_data_only(self, mocker):
        """Test measurements returns only the current user's data."""
        # Given two users with measurements
        user1 = User.objects.create_user(
            email="user1@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        user2 = User.objects.create_user(
            email="user2@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=175.0,
        )
        Measurement.objects.create(user=user1, body_fat_perc=20.0, weight=80.0)
        Measurement.objects.create(user=user2, body_fat_perc=25.0, weight=90.0)

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When querying measurements
        query = "{ measurements { id weight } }"
        result = schema.execute_sync(query, context_value=mock_context)

        # Then only user1's measurement is returned
        assert len(result.data["measurements"]) == 1
        assert result.data["measurements"][0]["weight"] == 80.0

    def test_measurement_detail(self, mocker):
        """Test single measurement query."""
        # Given a user with a measurement
        user = User.objects.create_user(
            email="detail@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=18.0, weight=75.0
        )

        # And the user is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When querying for a specific measurement
        query = """
            query GetMeasurement($id: ID!) {
                measurement(id: $id) {
                    id
                    bodyFatPerc
                    weight
                    bmr
                }
            }
        """
        result = schema.execute_sync(
            query,
            variable_values={"id": str(measurement.id)},
            context_value=mock_context,
        )

        # Then the measurement is returned with computed fields
        assert result.data["measurement"]["bodyFatPerc"] == 18.0
        assert result.data["measurement"]["weight"] == 75.0
        assert result.data["measurement"]["bmr"] is not None

    def test_measurement_not_found(self, mocker):
        """Test measurement query when ID doesn't exist."""
        # Given an authenticated user
        user = User.objects.create_user(
            email="notfound@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When querying for a non-existent measurement
        query = """
            query GetMeasurement($id: ID!) {
                measurement(id: $id) { id }
            }
        """
        result = schema.execute_sync(
            query,
            variable_values={"id": "99999"},
            context_value=mock_context,
        )

        # Then None is returned
        assert result.data["measurement"] is None

    def test_cannot_access_other_users_measurement(self, mocker):
        """Test that a user cannot access another user's measurement."""
        # Given two users, where user2 has a measurement
        user1 = User.objects.create_user(
            email="access1@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        user2 = User.objects.create_user(
            email="access2@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=175.0,
        )
        measurement = Measurement.objects.create(
            user=user2, body_fat_perc=20.0, weight=80.0
        )

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When user1 tries to access user2's measurement
        query = """
            query GetMeasurement($id: ID!) {
                measurement(id: $id) { id }
            }
        """
        result = schema.execute_sync(
            query,
            variable_values={"id": str(measurement.id)},
            context_value=mock_context,
        )

        # Then None is returned
        assert result.data["measurement"] is None


@pytest.mark.django_db
class TestCreateMeasurement:
    """Tests for create measurement mutation."""

    def test_create_measurement(self, mocker):
        """Test creating a measurement."""
        # Given an authenticated user
        user = User.objects.create_user(
            email="create@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When creating a measurement
        mutation = """
            mutation CreateMeasurement(
                $bodyFatPerc: Float!,
                $weight: Float!
            ) {
                createMeasurement(
                    bodyFatPerc: $bodyFatPerc,
                    weight: $weight
                ) {
                    id
                    bodyFatPerc
                    weight
                    bmr
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "bodyFatPerc": 22.5,
                "weight": 85.0,
            },
            context_value=mock_context,
        )

        # Then the measurement is created successfully
        assert result.errors is None
        data = result.data["createMeasurement"]
        assert data["bodyFatPerc"] == 22.5
        assert data["weight"] == 85.0
        assert data["bmr"] is not None

        # And it exists in the database
        assert Measurement.objects.filter(user=user).count() == 1

    def test_create_measurement_unauthenticated(self):
        """Test creating a measurement without authentication."""
        # When creating a measurement without auth
        mutation = """
            mutation {
                createMeasurement(
                    bodyFatPerc: 22.5,
                    weight: 85.0
                ) { id }
            }
        """
        result = schema.execute_sync(mutation, context_value=None)

        # Then an error is returned
        assert result.errors is not None

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("weight", 0.0),
            ("weight", -1.0),
            ("weight", float("nan")),
            ("weight", float("inf")),
            ("weight", -float("inf")),
            ("bodyFatPerc", 0.0),
            ("bodyFatPerc", -1.0),
            ("bodyFatPerc", 100.0),
            ("bodyFatPerc", 100.1),
            ("bodyFatPerc", float("nan")),
            ("bodyFatPerc", float("inf")),
            ("bodyFatPerc", -float("inf")),
        ],
    )
    def test_create_measurement_rejects_invalid_values_without_persisting(
        self, mocker, field, value
    ):
        """Creating a measurement requires physiological finite values."""
        user = User.objects.create_user(
            email=f"invalid-create-{field}-{repr(value)}@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateMeasurement(
                $bodyFatPerc: Float!, $weight: Float!
            ) {
                createMeasurement(
                    bodyFatPerc: $bodyFatPerc, weight: $weight
                ) { id }
            }
        """
        variables = {"bodyFatPerc": 20.0, "weight": 80.0}
        variables[field] = value

        result = schema.execute_sync(
            mutation,
            variable_values=variables,
            context_value=mock_context,
        )

        assert result.errors is not None
        assert not Measurement.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestUpdateMeasurement:
    """Tests for update measurement mutation."""

    def test_update_measurement(self, mocker):
        """Test updating a measurement."""
        # Given a user with an existing measurement
        user = User.objects.create_user(
            email="update@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20.0, weight=80.0
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When updating the measurement
        mutation = """
            mutation UpdateMeasurement(
                $id: ID!,
                $bodyFatPerc: Float!,
                $weight: Float!
            ) {
                updateMeasurement(
                    id: $id,
                    bodyFatPerc: $bodyFatPerc,
                    weight: $weight
                ) {
                    bodyFatPerc
                    weight
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(measurement.id),
                "bodyFatPerc": 19.0,
                "weight": 78.5,
            },
            context_value=mock_context,
        )

        # Then the measurement is updated
        assert result.errors is None
        assert result.data["updateMeasurement"]["bodyFatPerc"] == 19.0
        assert result.data["updateMeasurement"]["weight"] == 78.5

        # And the database reflects the changes
        measurement.refresh_from_db()
        assert float(measurement.body_fat_perc) == 19.0
        assert float(measurement.weight) == 78.5

    def test_update_measurement_recalculates_all_referencing_plan_days(
        self, mocker
    ):
        """Measurement changes persist fresh energy and macro goals for 7 days."""
        user = User.objects.create_user(
            email="update-plan-goals@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20, weight=80
        )
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=datetime.date.today(),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=500,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateMeasurement($id: ID!) {
                updateMeasurement(
                    id: $id, bodyFatPerc: 10, weight: 100
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(measurement.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        days = list(Day.objects.filter(plan=plan).order_by("day_num"))
        assert len(days) == 7
        expected_bmr = Decimal("2314")
        expected_protein = Decimal("180.00")
        for day in days:
            expected_energy = (expected_bmr - day.deficit).quantize(
                Decimal("0.01")
            )
            expected_fat = (
                expected_energy * Decimal("0.25") / Decimal("9")
            ).quantize(Decimal("0.01"))
            expected_carbs = (
                (
                    expected_energy
                    - expected_energy * Decimal("0.25")
                    - expected_protein * Decimal("4")
                )
                / Decimal("4")
            ).quantize(Decimal("0.01"))
            assert (
                day.energy_kcal_goal,
                day.protein_g_goal,
                day.fat_g_goal,
                day.carbs_g_goal,
            ) == (
                expected_energy,
                expected_protein,
                expected_fat,
                expected_carbs,
            )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("weight", 0.0),
            ("weight", -1.0),
            ("weight", float("nan")),
            ("weight", float("inf")),
            ("weight", -float("inf")),
            ("bodyFatPerc", 0.0),
            ("bodyFatPerc", -1.0),
            ("bodyFatPerc", 100.0),
            ("bodyFatPerc", 100.1),
            ("bodyFatPerc", float("nan")),
            ("bodyFatPerc", float("inf")),
            ("bodyFatPerc", -float("inf")),
        ],
    )
    def test_update_measurement_rejects_invalid_values_without_writes(
        self, mocker, field, value
    ):
        """Invalid updates do not persist or recalculate referencing days."""
        user = User.objects.create_user(
            email=f"invalid-update-{field}-{repr(value)}@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20, weight=80
        )
        plan = WeekPlan.objects.create(
            user=user,
            measurement=measurement,
            start_date=datetime.date.today(),
            protein_g_kg=Decimal("1.8"),
            fat_perc=Decimal("25"),
            deficit=500,
        )
        original_day_states = list(
            plan.days.order_by("id").values_list(
                "energy_kcal_goal",
                "protein_g_goal",
                "fat_g_goal",
                "carbs_g_goal",
            )
        )
        day_save = mocker.patch("apps.plans.models.Day.save", autospec=True)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateMeasurement(
                $id: ID!, $bodyFatPerc: Float!, $weight: Float!
            ) {
                updateMeasurement(
                    id: $id, bodyFatPerc: $bodyFatPerc, weight: $weight
                ) { id }
            }
        """
        variables = {
            "id": str(measurement.id),
            "bodyFatPerc": 20.0,
            "weight": 80.0,
        }
        variables[field] = value

        result = schema.execute_sync(
            mutation,
            variable_values=variables,
            context_value=mock_context,
        )

        assert result.errors is not None
        measurement.refresh_from_db()
        assert measurement.body_fat_perc == Decimal("20.0")
        assert measurement.weight == Decimal("80.0")
        assert (
            list(
                plan.days.order_by("id").values_list(
                    "energy_kcal_goal",
                    "protein_g_goal",
                    "fat_g_goal",
                    "carbs_g_goal",
                )
            )
            == original_day_states
        )
        day_save.assert_not_called()

    def test_cannot_update_other_users_measurement(self, mocker):
        """Test that a user cannot update another user's measurement."""
        # Given two users, where user2 has a measurement
        user1 = User.objects.create_user(
            email="upd1@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        user2 = User.objects.create_user(
            email="upd2@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=175.0,
        )
        measurement = Measurement.objects.create(
            user=user2, body_fat_perc=20.0, weight=80.0
        )

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When user1 tries to update user2's measurement
        mutation = """
            mutation UpdateMeasurement(
                $id: ID!,
                $bodyFatPerc: Float!,
                $weight: Float!
            ) {
                updateMeasurement(
                    id: $id,
                    bodyFatPerc: $bodyFatPerc,
                    weight: $weight
                ) { id }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(measurement.id),
                "bodyFatPerc": 15.0,
                "weight": 70.0,
            },
            context_value=mock_context,
        )

        # Then an error is returned
        assert result.errors is not None


@pytest.mark.django_db
class TestDeleteMeasurement:
    """Tests for delete measurement mutation."""

    def test_delete_measurement(self, mocker):
        """Test deleting a measurement."""
        # Given a user with an existing measurement
        user = User.objects.create_user(
            email="delete@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        measurement = Measurement.objects.create(
            user=user, body_fat_perc=20.0, weight=80.0
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When deleting the measurement
        mutation = """
            mutation DeleteMeasurement($id: ID!) {
                deleteMeasurement(id: $id)
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(measurement.id)},
            context_value=mock_context,
        )

        # Then the mutation returns true
        assert result.errors is None
        assert result.data["deleteMeasurement"] is True

        # And the measurement is removed from the database
        assert not Measurement.objects.filter(pk=measurement.id).exists()

    def test_cannot_delete_other_users_measurement(self, mocker):
        """Test that a user cannot delete another user's measurement."""
        # Given two users, where user2 has a measurement
        user1 = User.objects.create_user(
            email="del1@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        user2 = User.objects.create_user(
            email="del2@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=175.0,
        )
        measurement = Measurement.objects.create(
            user=user2, body_fat_perc=20.0, weight=80.0
        )

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When user1 tries to delete user2's measurement
        mutation = """
            mutation DeleteMeasurement($id: ID!) {
                deleteMeasurement(id: $id)
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(measurement.id)},
            context_value=mock_context,
        )

        # Then an error is returned
        assert result.errors is not None

        # And the measurement still exists
        assert Measurement.objects.filter(pk=measurement.id).exists()
