"""measurements app factories module."""


import datetime
from decimal import Decimal

from factory import SubFactory
from factory.django import DjangoModelFactory

from apps.measurements.models import Measurement

from ..users.factories import UserFactory


class MeasurementFactory(DjangoModelFactory):
    """MeasurementFactory class."""

    class Meta:
        model = Measurement

    user = SubFactory(UserFactory)
    created_at = datetime.datetime(
        2023,
        1,
        13,
        tzinfo=datetime.timezone.utc,
    )
    body_fat_perc = 21
    weight = Decimal("94.3")
