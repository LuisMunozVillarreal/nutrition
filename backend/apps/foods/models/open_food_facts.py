"""Persistence models for the Open Food Facts integration."""

from django.db import models


class OpenFoodFactsCacheEntry(models.Model):
    """Cache one provider product payload or a negative lookup."""

    barcode = models.CharField(max_length=14, primary_key=True)
    product = models.JSONField(null=True)
    expires_at = models.DateTimeField(db_index=True)


class OpenFoodFactsRateLimit(models.Model):
    """Coordinate provider read timestamps across backend replicas."""

    key = models.CharField(max_length=64, primary_key=True)
    request_timestamps = models.JSONField(default=list)
