"""Graphene schema."""


import graphene

from apps.foods.mutations import FoodsMutations
from apps.foods.queries import FoodProductQuery


class Query(FoodProductQuery, graphene.ObjectType):
    """Graphene queries."""


class Mutation(FoodsMutations, graphene.ObjectType):
    """Graphene mutations."""
    # pylint: disable=too-few-public-methods


SCHEMA = graphene.Schema(query=Query, mutation=Mutation)
