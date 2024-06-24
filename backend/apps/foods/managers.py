"""food app model managers."""

from django.db import models

from apps.foods.models.nutrients import NUTRIENT_LIST


class CupboardItemServingManager(models.Manager):
    """CupboardItemServing Manager class."""

    # pylint: disable=too-few-public-methods

    def create_from_serving(self, item, serving):
        """Create cupboard item serving from food serving.

        Args:
            item (CupboardItem): item to associate it to.
            serving (Serving): food serving to create from.

        Returns:
            CupboardItemServing: created instance.
        """
        fields = {
            "item": item,
            "food": serving.food,
            "size": serving.size,
            "unit": serving.unit,
        }
        for nutrient in NUTRIENT_LIST:
            fields[nutrient] = getattr(serving, nutrient)

        serving = self.model(**fields)
        serving.save(using=self.db)
        return serving
