"""users app admin config module."""


from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """UserAdmin class."""

    list_display = [
        "id",
        "full_name",
        "email",
        "date_of_birth",
        "height",
    ]
