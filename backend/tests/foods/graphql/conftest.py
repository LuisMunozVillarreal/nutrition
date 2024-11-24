"""tests.foods.graphql conftest."""


import pytest
from graphene_django.utils.testing import graphql_query


@pytest.fixture
def client_query(client):
    """Graphql Client query mock."""

    def func(*args, **kwargs):
        return graphql_query(*args, **kwargs, client=client)

    return func
