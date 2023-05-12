"""Food model module."""


from django.db import models

from .nutrients import Nutrients


class Food(Nutrients):
    """Food model class."""

    name = models.CharField(
        max_length=255,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return self.name
