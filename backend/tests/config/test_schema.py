"""Tests for GraphQL schema configuration."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.goals.models import FatPercGoal
from apps.measurements.models import Measurement
from config.schema import schema

User = get_user_model()


def bearer_context(user_id, session_user=None):
    """Build a GraphQL request context carrying a signed bearer token."""
    token = jwt.encode(
        {
            "sub": str(user_id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    request = RequestFactory().post(
        "/graphql/", HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    request.user = session_user or AnonymousUser()
    return request


@pytest.mark.django_db
def test_hello_query():
    """Test hello query resolver."""
    # When executing a hello query
    query = "{ hello }"
    result = schema.execute_sync(query)

    # Then the result is correct
    assert result.data["hello"] == "world"


@pytest.mark.django_db
def test_me_query_unauthenticated():
    """Test me query resolver when not authenticated."""
    # When executing a me query without authentication
    query = "{ me { id email } }"
    result = schema.execute_sync(query, context_value=None)

    # Then the result is None
    assert result.data["me"] is None


@pytest.mark.django_db
def test_me_query_with_anonymous_request():
    """Test me query with an anonymous Django request."""
    context = RequestFactory().post("/graphql/")
    context.user = AnonymousUser()

    result = schema.execute_sync("{ me { id email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"] is None


@pytest.mark.django_db
def test_me_query_authenticated():
    """Test me query resolver when authenticated."""
    # Given an authenticated user
    user = User.objects.create_user(
        email="me@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )

    # And a session-authenticated context
    mock_context = SimpleNamespace(user=user)

    # When executing a me query with authentication
    query = "{ me { email } }"
    result = schema.execute_sync(query, context_value=mock_context)

    # Then the result contains the user email
    assert result.data["me"]["email"] == "me@example.com"


@pytest.mark.django_db
def test_me_query_authenticated_by_bearer_token():
    """Test me query resolves the user identified by its bearer token."""
    user = User.objects.create_user(
        email="bearer@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    context = bearer_context(user.id)

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"]["email"] == "bearer@example.com"


@pytest.mark.django_db
def test_me_query_bearer_token_overrides_session_user():
    """Test a bearer identity takes precedence over a Django session."""
    bearer_user = User.objects.create_user(
        email="bearer@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    session_user = User.objects.create_user(
        email="session@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    context = bearer_context(bearer_user.id, session_user)

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"]["email"] == "bearer@example.com"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "authorization", ["Bearer", "Basic credentials", "Bearer invalid-token"]
)
def test_me_query_rejects_invalid_bearer_without_session_fallback(
    authorization,
):
    """Test an invalid bearer token cannot expose a session user."""
    session_user = User.objects.create_user(
        email="session@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    context = RequestFactory().post(
        "/graphql/", HTTP_AUTHORIZATION=authorization
    )
    context.user = session_user

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"] is None


@pytest.mark.django_db
def test_me_query_rejects_bearer_for_missing_user():
    """Test a valid token cannot authenticate a deleted user."""
    context = bearer_context(999999)

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"] is None


@pytest.mark.django_db
def test_me_query_rejects_bearer_for_inactive_user():
    """Test a bearer token cannot authenticate an inactive user."""
    user = User.objects.create_user(
        email="inactive@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
        is_active=False,
    )
    context = bearer_context(user.id)

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"] is None


@pytest.mark.django_db
def test_user_dashboard():
    """Test dashboard resolver in UserType."""
    # Given a user with measurements and goals
    user = User.objects.create_user(
        email="dash@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )

    # When querying for the user's dashboard (without actual data yet)
    query = """
        query {
            me {
                dashboard {
                    latestWeight
                    latestBodyFat
                    goalBodyFat
                }
            }
        }
    """
    # Use an authenticated session context
    mock_context = SimpleNamespace(user=user)

    result = schema.execute_sync(query, context_value=mock_context)

    # Then we get null values since no measurements exist
    assert result.data["me"]["dashboard"]["latestWeight"] is None

    # When we add a measurement and a goal
    Measurement.objects.create(user=user, weight=80.5, body_fat_perc=20.0)
    FatPercGoal.objects.create(user=user, body_fat_perc=15.0)

    # And query again
    result = schema.execute_sync(query, context_value=mock_context)

    # Then we get the real values
    dash = result.data["me"]["dashboard"]
    assert dash["latestWeight"] == 80.5
    assert dash["latestBodyFat"] == 20.0
    assert dash["goalBodyFat"] == 15.0


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_login_mutation_success():
    """Test login mutation with valid credentials."""
    # Given a set of user credentials
    email = "user@example.com"
    password = "password123"

    # When a user exists
    await sync_to_async(User.objects.create_user)(
        email=email,
        password=password,
        first_name="Test",
        last_name="User",
        date_of_birth="2000-01-01",
        height=170.0,
    )

    # And we attempt to login with those credentials
    mutation = """
        mutation login($email: String!, $password: String!) {
            login(email: $email, password: $password) {
                token
                user {
                    id
                    email
                    firstName
                    lastName
                }
            }
        }
    """

    result = await schema.execute(
        mutation, variable_values={"email": email, "password": password}
    )

    # Then there is no errors
    assert result.errors is None

    # And the result contains a token and correct user info
    data = result.data["login"]
    assert data["token"] is not None
    assert data["user"]["email"] == email


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_login_mutation_failure():
    """Test login mutation with invalid credentials."""
    # When attempting to login with invalid credentials
    mutation = """
        mutation login($email: String!, $password: String!) {
            login(email: $email, password: $password) {
                token
            }
        }
    """

    result = await schema.execute(
        mutation,
        variable_values={"email": "wrong@example.com", "password": "wrong"},
    )

    # Then the result contains errors and no data
    assert result.errors is not None
    assert result.data is None
