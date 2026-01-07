"""Garmin models module."""

from django.conf import settings
from django.db import models

from apps.libs.basemodel import BaseModel


class GarminCredential(BaseModel):
    """Garmin credential model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="garmin_credential",
    )

    access_token = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255)
    expires_at = models.BigIntegerField(
        help_text="Token expiration timestamp (seconds since epoch)"
    )
    garmin_user_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"Garmin Credential for {self.user}"
