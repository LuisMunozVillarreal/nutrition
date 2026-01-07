"""Garmin models module."""

from django.conf import settings
from django.db import models

from apps.libs.basemodel import BaseModel


class GarminCredential(BaseModel):
    """Garmin credential model.

    Attributes:
        user (User): user instance.
        access_token (str): OAuth 2.0 access token.
        refresh_token (str): OAuth 2.0 refresh token.
        expires_at (int): token expiration timestamp.
        garmin_user_id (str): Garmin user ID.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="garmin_credential",
        verbose_name="user",
    )

    access_token = models.CharField(
        max_length=255, verbose_name="access token"
    )
    refresh_token = models.CharField(
        max_length=255, verbose_name="refresh token"
    )
    expires_at = models.BigIntegerField(
        help_text="Token expiration timestamp (seconds since epoch)",
        verbose_name="expires at",
    )
    garmin_user_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="garmin user id",
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"Garmin Credential for {self.user}"


class GarminActivity(BaseModel):
    """Garmin activity model.

    Attributes:
        exercise (Exercise): exercise instance.
        garmin_activity_id (str): Garmin activity ID.
        data (dict): raw activity data.
    """

    exercise = models.OneToOneField(
        "exercises.Exercise",
        on_delete=models.CASCADE,
        related_name="garmin_activity",
        verbose_name="exercise",
    )

    garmin_activity_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="garmin activity id",
    )

    data = models.JSONField(
        default=dict,
        verbose_name="data",
    )

    def __str__(self) -> str:
        """Get string representation.

        Returns:
            str: string representation.
        """
        return f"Garmin Activity {self.garmin_activity_id}"
