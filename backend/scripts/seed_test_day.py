"""Seed day data for the least-privileged E2E account."""

import datetime
import os
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.measurements.models import Measurement  # noqa: E402
from apps.plans.models import WeekPlan  # noqa: E402
from apps.users.models import User  # noqa: E402

user = User.objects.get(email=os.environ["E2E_REGULAR_EMAIL"])
if user.is_staff or user.is_superuser:
    raise RuntimeError("The regular E2E identity must remain least-privileged")

measurement = Measurement.objects.filter(user=user).first()
if not measurement:
    measurement = Measurement.objects.create(
        user=user,
        weight=Decimal("80"),
        body_fat_perc=Decimal("20"),
    )

plan = WeekPlan.objects.filter(user=user).first()
if not plan:
    plan = WeekPlan.objects.create(
        user=user,
        start_date=datetime.date.today(),
        protein_g_kg=Decimal("2"),
        fat_perc=Decimal("25"),
        deficit=0,
        measurement=measurement,
    )

day = plan.days.order_by("id").first()
print(day.id if day else "1")
