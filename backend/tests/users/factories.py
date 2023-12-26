"""apps.users factories."""


import datetime

from django.contrib.auth import get_user_model
from factory import Sequence
from factory.django import DjangoModelFactory


class UserFactory(DjangoModelFactory):
    """User factory class."""

    class Meta:
        model = get_user_model()

    email = Sequence(lambda n: f"test{n}@test.com")
    password = "password"
    date_of_birth = datetime.date(1985, 9, 12)
    height = 183
    first_name = Sequence(lambda n: f"first_name_{n}")
    last_name = Sequence(lambda n: f"last_name_{n}")
    is_staff = False
    is_superuser = False
