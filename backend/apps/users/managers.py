"""User models managers."""


from typing import Any

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager[AbstractUser]):
    """Custom user model manager.

    Email is the unique identifiers for authentication instead of usernames.
    """

    def __create_user(
        self, email: str, password: str, **extra_fields: Any
    ) -> AbstractUser:
        """Create and save a User with the given parameters.

        Args:
            email (str): user email.
            password (str): user password.
            extra_fields (dict): user extra fields.

        Returns:
            User: created user.

        Raises:
            ValueError: if email is not provided.
        """
        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, password=password, **extra_fields)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str, password: str, **extra_fields: Any
    ) -> AbstractUser:
        """Create and save a User with the given email and password.

        Args:
            email (str): user email.
            password (str): user password.
            extra_fields (dict): user extra fields.

        Returns:
            User: created user.
        """
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self.__create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str, **extra_fields: Any
    ) -> AbstractUser:
        """Create and save a SuperUser with the given email and password.

        Args:
            email (str): user email.
            password (str): user password.
            extra_fields (dict): user extra fields.

        Returns:
            User: created superuser.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        return self.__create_user(email, password, **extra_fields)
