"""Tests for GraphQL schema configuration."""

import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.goals.models import FatPercGoal
from apps.measurements.models import Measurement
from config.schema import authenticated_session_user, schema

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
@pytest.mark.parametrize("is_staff", [False, True])
def test_login_exposes_staff_capability(is_staff):
    """Login identifies regular and staff sessions without granting extra privilege."""
    email = f"capability-{str(is_staff).lower()}@example.com"
    password = secrets.token_urlsafe(24)
    User.objects.create_user(
        email=email,
        password=password,
        date_of_birth="2000-01-01",
        height=170.0,
        is_staff=is_staff,
    )

    result = schema.execute_sync(
        """
        mutation Login($email: String!, $password: String!) {
            login(email: $email, password: $password) {
                user { isStaff }
            }
        }
        """,
        variable_values={"email": email, "password": password},
    )

    assert result.errors is None
    assert result.data["login"]["user"]["isStaff"] is is_staff


@pytest.mark.django_db
def test_graphql_http_view_executes_login(client):
    """Test the configured HTTP view can execute authentication resolvers."""
    email = "http-login@example.com"
    password = "password123"
    User.objects.create_user(
        email=email,
        password=password,
        date_of_birth="2000-01-01",
        height=170.0,
    )

    response = client.post(
        "/graphql/",
        data={
            "query": """
                mutation Login($email: String!, $password: String!) {
                    login(email: $email, password: $password) {
                        token
                        user { email }
                    }
                }
            """,
            "variables": {"email": email, "password": password},
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert "errors" not in payload
    assert payload["data"]["login"]["user"]["email"] == email


@pytest.mark.django_db
def test_app_schema_authentication_accepts_request_context():
    """Test app resolvers authenticate a direct Django request context."""
    user = User.objects.create_user(
        email="request-context@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    Measurement.objects.create(user=user, weight=80, body_fat_perc=20)
    request = RequestFactory().post("/graphql/")
    request.user = user

    result = schema.execute_sync(
        "{ measurements { weight bodyFatPerc } }", context_value=request
    )

    assert result.errors is None
    assert result.data["measurements"] == [
        {"weight": 80.0, "bodyFatPerc": 20.0}
    ]


def test_authenticated_session_user_helper():
    """Test synchronous resolution for non-request GraphQL contexts."""
    authenticated = SimpleNamespace(is_authenticated=True)

    assert (
        authenticated_session_user(SimpleNamespace(user=authenticated))
        is authenticated
    )
    anonymous_context = SimpleNamespace(user=AnonymousUser())
    assert authenticated_session_user(anonymous_context) is None
    assert authenticated_session_user(SimpleNamespace()) is None


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
def test_me_query_resolves_session_user_from_wrapped_request():
    """Test session fallback accepts Strawberry's wrapped request context."""
    user = User.objects.create_user(
        email="async-session@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    context = SimpleNamespace(request=SimpleNamespace(user=user))

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"]["email"] == "async-session@example.com"


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
def test_me_query_bearer_token_works_in_sync_execution():
    """Test bearer authentication works in the configured sync path."""
    user = User.objects.create_user(
        email="async-bearer@example.com",
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )
    context = bearer_context(user.id)

    result = schema.execute_sync("{ me { email } }", context_value=context)

    assert result.errors is None
    assert result.data["me"]["email"] == "async-bearer@example.com"


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
def test_login_mutation_success():
    """Test login mutation with valid credentials."""
    # Given a set of user credentials
    email = "user@example.com"
    password = "password123"

    # When a user exists
    User.objects.create_user(
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

    result = schema.execute_sync(
        mutation, variable_values={"email": email, "password": password}
    )

    # Then there is no errors
    assert result.errors is None

    # And the result contains a token and correct user info
    data = result.data["login"]
    assert data["token"] is not None
    assert data["user"]["email"] == email


@pytest.mark.django_db
def test_login_mutation_failure():
    """Test login mutation with invalid credentials."""
    # When attempting to login with invalid credentials
    mutation = """
        mutation login($email: String!, $password: String!) {
            login(email: $email, password: $password) {
                token
            }
        }
    """

    result = schema.execute_sync(
        mutation,
        variable_values={"email": "wrong@example.com", "password": "wrong"},
    )

    # Then the result contains errors and no data
    assert result.errors is not None
    assert result.data is None
