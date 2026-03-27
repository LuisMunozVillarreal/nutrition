"""Tests for Goals GraphQL schema."""

import pytest
from django.contrib.auth import get_user_model

from apps.goals.models import FatPercGoal
from config.schema import schema

User = get_user_model()


@pytest.mark.django_db
class TestGoalsQuery:
    """Tests for goal queries."""

    def test_goals_unauthenticated(self):
        """Test goals query without authentication."""
        # When querying goals without auth
        query = "{ fatPercGoals { id } }"
        result = schema.execute_sync(query, context_value=None)

        # Then the result is an empty list
        assert result.data["fatPercGoals"] == []

    def test_goals_returns_user_data_only(self, mocker):
        """Test goals returns only the current user's data."""
        # Given two users with goals
        user1 = User.objects.create_user(
            email="goal1@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        user2 = User.objects.create_user(
            email="goal2@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=175.0,
        )
        FatPercGoal.objects.create(user=user1, body_fat_perc=15.0)
        FatPercGoal.objects.create(user=user2, body_fat_perc=12.0)

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When querying goals
        query = "{ fatPercGoals { id bodyFatPerc } }"
        result = schema.execute_sync(query, context_value=mock_context)

        # Then only user1's goal is returned
        assert len(result.data["fatPercGoals"]) == 1
        assert result.data["fatPercGoals"][0]["bodyFatPerc"] == 15.0

    def test_goal_detail(self, mocker):
        """Test single goal query."""
        # Given a user with a goal
        user = User.objects.create_user(
            email="goaldetail@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        goal = FatPercGoal.objects.create(user=user, body_fat_perc=15.0)

        # And the user is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When querying for a specific goal
        query = """
            query GetGoal($id: ID!) {
                fatPercGoal(id: $id) {
                    id
                    bodyFatPerc
                }
            }
        """
        result = schema.execute_sync(
            query,
            variable_values={"id": str(goal.id)},
            context_value=mock_context,
        )

        # Then the goal is returned
        assert result.data["fatPercGoal"]["bodyFatPerc"] == 15.0


@pytest.mark.django_db
class TestCreateGoal:
    """Tests for create goal mutation."""

    def test_create_goal(self, mocker):
        """Test creating a goal."""
        # Given an authenticated user
        user = User.objects.create_user(
            email="goalcreate@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When creating a goal
        mutation = """
            mutation CreateGoal($bodyFatPerc: Float!) {
                createFatPercGoal(bodyFatPerc: $bodyFatPerc) {
                    id
                    bodyFatPerc
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"bodyFatPerc": 14.0},
            context_value=mock_context,
        )

        # Then the goal is created
        assert result.errors is None
        assert result.data["createFatPercGoal"]["bodyFatPerc"] == 14.0
        assert FatPercGoal.objects.filter(user=user).count() == 1


@pytest.mark.django_db
class TestUpdateGoal:
    """Tests for update goal mutation."""

    def test_update_goal(self, mocker):
        """Test updating a goal."""
        # Given a user with an existing goal
        user = User.objects.create_user(
            email="goalupdate@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        goal = FatPercGoal.objects.create(user=user, body_fat_perc=15.0)
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When updating the goal
        mutation = """
            mutation UpdateGoal($id: ID!, $bodyFatPerc: Float!) {
                updateFatPercGoal(id: $id, bodyFatPerc: $bodyFatPerc) {
                    bodyFatPerc
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(goal.id),
                "bodyFatPerc": 12.0,
            },
            context_value=mock_context,
        )

        # Then the goal is updated
        assert result.errors is None
        assert result.data["updateFatPercGoal"]["bodyFatPerc"] == 12.0

    def test_cannot_update_other_users_goal(self, mocker):
        """Test that a user cannot update another user's goal."""
        # Given two users, where user2 has a goal
        user1 = User.objects.create_user(
            email="gu1@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        user2 = User.objects.create_user(
            email="gu2@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=175.0,
        )
        goal = FatPercGoal.objects.create(user=user2, body_fat_perc=15.0)

        # And user1 is authenticated
        mock_context = mocker.Mock()
        mock_context.request.user = user1

        # When user1 tries to update user2's goal
        mutation = """
            mutation UpdateGoal($id: ID!, $bodyFatPerc: Float!) {
                updateFatPercGoal(
                    id: $id,
                    bodyFatPerc: $bodyFatPerc
                ) { id }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(goal.id),
                "bodyFatPerc": 10.0,
            },
            context_value=mock_context,
        )

        # Then an error is returned
        assert result.errors is not None


@pytest.mark.django_db
class TestDeleteGoal:
    """Tests for delete goal mutation."""

    def test_delete_goal(self, mocker):
        """Test deleting a goal."""
        # Given a user with an existing goal
        user = User.objects.create_user(
            email="goaldelete@example.com",
            password="password123",
            date_of_birth="2000-01-01",
            height=170.0,
        )
        goal = FatPercGoal.objects.create(user=user, body_fat_perc=15.0)
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When deleting the goal
        mutation = """
            mutation DeleteGoal($id: ID!) {
                deleteFatPercGoal(id: $id)
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(goal.id)},
            context_value=mock_context,
        )

        # Then the mutation succeeds
        assert result.errors is None
        assert result.data["deleteFatPercGoal"] is True

        # And the goal is deleted
        assert not FatPercGoal.objects.filter(pk=goal.id).exists()
