"""FoodQuantity model module."""


from django.db import models


class FoodQuantity(models.Model):
    """FoodQuantity model class."""

    class Meta:
        abstract = True

    serving_size = models.PositiveIntegerField(
        default=100,
    )

    SERVING_UNIT_GRAMS = "g"
    SERVING_UNIT_MILIGRAMS = "mg"
    SERVING_UNIT_CHOICES = (
        (SERVING_UNIT_GRAMS, "gram(s)"),
        (SERVING_UNIT_MILIGRAMS, "miligram(s)"),
    )

    serving_unit = models.CharField(
        max_length=20,
        choices=SERVING_UNIT_CHOICES,
        default=SERVING_UNIT_GRAMS,
    )
