"""Add cupboard ownership and reconcile legacy inventory deterministically."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assign_legacy_cupboard_owner(apps, schema_editor):
    """Assign legacy inventory without exposing it to every account.

    Existing rows predate per-user ownership. If accounts exist, all such rows
    are assigned to the earliest privileged account (staff or superuser), or
    otherwise the earliest account. ``date_joined`` and then the primary key
    provide deterministic ordering. With no account available rows remain null
    so fresh or partially restored installations can still migrate.
    """
    del schema_editor
    cupboard_item = apps.get_model("foods", "CupboardItem")
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    user = apps.get_model(user_app, user_model)

    owner = (
        user.objects.filter(
            models.Q(is_staff=True) | models.Q(is_superuser=True)
        )
        .order_by("date_joined", "pk")
        .first()
    )
    if owner is None:
        owner = user.objects.order_by("date_joined", "pk").first()
    if owner is not None:
        cupboard_item.objects.filter(owner__isnull=True).update(
            owner_id=owner.pk
        )


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
        migrations.RunPython(
            assign_legacy_cupboard_owner,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
