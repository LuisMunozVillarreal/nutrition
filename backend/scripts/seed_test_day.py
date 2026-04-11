import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.users.models import User
from apps.measurements.models import Measurement
from apps.plans.models import WeekPlan, Day
import datetime
from decimal import Decimal

# Ensure user exists
try:
    u = User.objects.get(email='user@example.com')
except User.DoesNotExist:
    u = User.objects.create_user(email='user@example.com', password='password123', first_name='Nutrition', last_name='User', date_of_birth=datetime.date(1990, 1, 1), height=180.0)

m = Measurement.objects.filter(user=u).first()
if not m:
    m = Measurement.objects.create(user=u, weight=Decimal('80'), body_fat_perc=Decimal('20'))

p = WeekPlan.objects.filter(user=u).first()
if not p:
    p = WeekPlan.objects.create(user=u, start_date=datetime.date.today(), protein_g_kg=Decimal('2'), fat_perc=Decimal('25'), deficit=0, measurement=m)

d = p.days.order_by('id').first()
# For some reason in the signals it uses day_set or days? 
# In models it's Day (ForeignKey to plan).
# Django default related_name is day_set but it is overridden to days.
print(d.id if d else '1')
