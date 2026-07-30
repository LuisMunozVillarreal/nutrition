"""Add nullable cupboard ownership for legacy-row compatibility."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the cupboard item owner relationship."""

    dependencies = [
        ("foods", "0030_alter_food_carbs_g_alter_food_fat_g_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cupboarditem",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cupboard_items",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
