
import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.users.models import User

if not User.objects.filter(email='test@example.com').exists():
    User.objects.create_user(
        email='test@example.com',
        password='password',
        first_name='Test',
        last_name='User',
        date_of_birth='1990-01-01',
        height=180.0
    )
    print("Created test user")
else:
    print("Test user already exists")
