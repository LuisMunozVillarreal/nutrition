# Generated by Django 4.2 on 2023-05-05 22:35

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("measurements", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]