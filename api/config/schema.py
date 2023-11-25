import graphene


from apps.foods.mutations import FoodsMutations
from apps.foods.queries import FoodProductQuery


class Query(FoodProductQuery, graphene.ObjectType):
    pass


class Mutation(FoodsMutations, graphene.ObjectType):
    pass


SCHEMA = graphene.Schema(query=Query, mutation=Mutation)
