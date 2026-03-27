from apps.foods.models import FoodProduct
from graphql import graphql_sync
from config.schema import schema
from django.contrib.auth import get_user_model

user = get_user_model().objects.first()

query = """
  mutation CreateFoodProduct(
    $name: String!, $notes: String!,
    $nutritionalInfoSize: Float!, $nutritionalInfoUnit: String!,
    $size: Float!, $sizeUnit: String!, $numServings: Float!,
    $energyKcal: Float!, $proteinG: Float!, $fatG: Float!, $carbsG: Float!
  ) {
    createFoodProduct(
      name: $name, notes: $notes,
      nutritionalInfoSize: $nutritionalInfoSize, nutritionalInfoUnit: $nutritionalInfoUnit,
      size: $size, sizeUnit: $sizeUnit, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG
    ) { id }
  }
"""
variables = {
    'name': 'Oats', 'notes': '',
    'nutritionalInfoSize': 100, 'nutritionalInfoUnit': 'g',
    'size': 100, 'sizeUnit': 'g', 'numServings': 1.0,
    'energyKcal': 370, 'proteinG': 0, 'fatG': 0, 'carbsG': 0
}

class Context:
    def __init__(self, user):
        self.user = user

result = schema.execute_sync(query, variable_values=variables, context_value=Context(user))
print('ERRORS:', result.errors)
print('DATA:', result.data)
