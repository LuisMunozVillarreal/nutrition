"""users app admin config module."""

from django.contrib import admin

from apps.libs.admin import round_field

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """UserAdmin class."""

    search_fields = [
        "first_name",
        "last_name",
    ]

    list_display = [
        "id",
        "full_name",
        "email",
        "date_of_birth",
        round_field("height"),
    ]
