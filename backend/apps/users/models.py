"""User model module."""


from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.libs.basemodel import BaseModel

from .managers import UserManager


class User(AbstractUser, BaseModel):
    """User model."""

    objects = UserManager()  # type: ignore

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = [
        field
        for field in AbstractUser.REQUIRED_FIELDS
        if field
        not in (
            "username",
            "email",
        )
    ]

    username = None  # type: ignore

    email = models.EmailField(
        unique=True,
    )

    date_of_birth = models.DateField()

    height = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        help_text="Height (cm)",
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: user's full name.
        """
        return self.full_name

    @property
    def full_name(self) -> str:
        """Get User's full name.

        Returns:
            str: User's full name.
        """
        if self.last_name:
            return self.get_full_name()

        return self.first_name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save user attributes.

        Args:
            args (list): arguments.
            kwargs (dict): keywords arguments.
        """
        created = self.id is None
        if created:
            self.email = self.email.lower()
            self.set_password(self.password)
        else:
            if (
                self._password is None  # type: ignore
                and not self.check_password(self.password)
            ):
                self.set_password(self.password)

        super().save(*args, **kwargs)
