"""Tests for GraphQL schema configuration."""

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

from config.schema import schema

User = get_user_model()


@pytest.mark.django_db
def test_hello_query():
    """Test hello query resolver."""
    # When executing a hello query
    query = "{ hello }"
    result = schema.execute_sync(query)

    # Then the result is correct
    assert result.data["hello"] == "world"


@pytest.mark.django_db
def test_me_query():
    """Test me query resolver (placeholder)."""
    # When executing a me query
    query = "{ me }"
    result = schema.execute_sync(query)

    # Then the result is the placeholder
    assert result.data["me"] == "Not implemented fully yet"


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
