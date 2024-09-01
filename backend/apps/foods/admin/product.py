"""admin config for food products module."""

from decimal import Decimal
from typing import Dict

from django import forms
from django.contrib import admin

from apps.foods.ocado_scraper import get_ocado_product_details
from apps.libs.admin import get_remaining_fields

from ..models import FoodProduct
from .serving import ServingInline


class FoodProductForm(forms.ModelForm):
    """FoodProduct Form class."""

    class Meta:
        model = FoodProduct
        fields = "__all__"

    scrape_info_from_url = forms.BooleanField(required=False)

    def clean(self) -> Dict[str, str | Decimal]:
        """Add scraped info to the fields if requested.

        Returns:
            Dict[str, str | Decimal]

        Raises:
            ValidationError: if scraping is requested but URL isn't provided.
        """
        if self.cleaned_data.get("scrape_info_from_url"):
            url = self.cleaned_data.get("url")
            if not url:
                raise forms.ValidationError(
                    "URL is required to scrape the info from"
                )

            if url[:31] != "https://www.ocado.com/products/":
                raise forms.ValidationError(
                    "Only Ocado product URLs are supported"
                )

            data = get_ocado_product_details(url)

            del self.errors["name"]

            self.cleaned_data["brand"] = data["brand"]
            self.cleaned_data["name"] = data["name"]
            self.cleaned_data["weight"] = round(Decimal(str(data["size"])), 1)
            self.cleaned_data["weight_unit"] = data["size unit"]
            self.cleaned_data["num_servings"] = (
                data["servings"] or self.cleaned_data["num_servings"]
            )
            self.cleaned_data["energy"] = round(Decimal(str(data["kcal"])), 1)
            self.cleaned_data["fat_g"] = round(Decimal(str(data["fat"])), 1)
            self.cleaned_data["saturated_fat_g"] = round(
                Decimal(str(data["saturates"])), 1
            )
            self.cleaned_data["carbs_g"] = round(
                Decimal(str(data["carbohydrates"])), 1
            )
            self.cleaned_data["sugar_carbs_g"] = round(
                Decimal(str(data["sugars"])), 1
            )
            self.cleaned_data["fibre_carbs_g"] = round(
                Decimal(str(data["fibre"])), 1
            )
            self.cleaned_data["protein_g"] = round(
                Decimal(str(data["protein"])), 1
            )
            self.cleaned_data["salt_g"] = round(Decimal(str(data["salt"])), 1)
            self.cleaned_data["nutritional_info_unit"] = data["size unit"]

        return self.cleaned_data


@admin.register(FoodProduct)
class FoodProductAdmin(admin.ModelAdmin):
    """FoodProductAdmin class."""

    # pylint: disable=duplicate-code

    form = FoodProductForm

    inlines = [
        ServingInline,
    ]

    search_fields = [
        "brand",
        "name",
    ]

    list_display = [
        "id",
        "brand",
        "name",
        "weight",
        "weight_unit",
        "num_servings",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
    ]

    _main_fields = [
        "brand",
        "name",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
        "url",
        "barcode",
        "nutritional_info_size",
        "nutritional_info_unit",
        "weight",
        "weight_unit",
        "num_servings",
    ]

    fieldsets = [
        (
            "General",
            {
                "fields": [
                    "brand",
                    "name",
                    "url",
                    "scrape_info_from_url",
                    "barcode",
                    "weight",
                    "weight_unit",
                    "num_servings",
                ],
            },
        ),
        (
            "Nutrition",
            {
                "fields": [
                    "nutritional_info_size",
                    "nutritional_info_unit",
                    "energy",
                    "fat_g",
                    "carbs_g",
                    "protein_g",
                ],
            },
        ),
        (
            "Extra nutrients",
            {
                "classes": ["collapse"],
                "fields": get_remaining_fields(FoodProduct, _main_fields),
            },
        ),
    ]
