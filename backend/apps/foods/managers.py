from django.db import models

from apps.foods.models.nutrients import NUTRIENT_LIST


class CupboardItemServingManager(models.Manager):
    def create_from_serving(self, item, serving):
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
