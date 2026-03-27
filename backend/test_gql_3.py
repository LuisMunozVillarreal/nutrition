import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from config.schema import schema
from django.contrib.auth import get_user_model

user = get_user_model().objects.first()

query = """
  query {
    foodProducts {
      id name brand size sizeUnit
    }
  }
"""

class Context:
    def __init__(self, user):
        self.user = user

result = schema.execute_sync(query, context_value=Context(user))
print('ERRORS:', result.errors)
if result.data:
    print('DATA LENGTH:', len(result.data['foodProducts']))
