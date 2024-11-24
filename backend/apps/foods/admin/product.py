"""admin config for food products module."""

from decimal import Decimal
from typing import Dict

from django import forms
from django.contrib import admin

from apps.foods.nutrition_facts_finder import (
    get_food_nutrition_facts,
    get_ocado_product_details,
)
from apps.libs.admin import get_remaining_fields

from ..models import FoodProduct
from .base import TagsAdminMixin
from .serving import ServingInline


class FoodProductForm(forms.ModelForm):
    """FoodProduct Form class."""

    class Meta:
        model = FoodProduct
        fields = "__all__"

    scrape_info_from_url = forms.BooleanField(required=False)
    get_info_with_gemini = forms.BooleanField(required=False)

    def _clean_nutrition_facts(self, data: Dict[str, float]) -> None:
        """Clean nutrition facts.

        Args:
            data (Dict[str, float]): nutrition facts.
        """
        self.cleaned_data["energy"] = round(
            Decimal(
                str(data["kcal"] or self.cleaned_data.get("energy", 0) or 0)
            ),
            1,
        )
        self.cleaned_data["fat_g"] = round(
            Decimal(
                str(data["fat"] or self.cleaned_data.get("fat_g", 0) or 0)
            ),
            1,
        )
        self.cleaned_data["saturated_fat_g"] = round(
            Decimal(
                str(
                    data["saturates"]
                    or self.cleaned_data.get("saturated_fat_g", 0)
                    or 0
                )
            ),
            1,
        )
        self.cleaned_data["carbs_g"] = round(
            Decimal(
                str(
                    data["carbohydrates"]
                    or self.cleaned_data.get("carbs_g", 0)
                    or 0
                )
            ),
            1,
        )
        self.cleaned_data["sugar_carbs_g"] = round(
            Decimal(
                str(
                    data["sugars"]
                    or self.cleaned_data.get("sugars_carbs_g", 0)
                    or 0
                )
            ),
            1,
        )
        self.cleaned_data["fibre_carbs_g"] = round(
            Decimal(
                str(
                    data["fibre"]
                    or self.cleaned_data.get("fibre_carbs_g", 0)
                    or 0
                )
            ),
            1,
        )
        self.cleaned_data["protein_g"] = round(
            Decimal(
                str(
                    data["protein"]
                    or self.cleaned_data.get("protein_g", 0)
                    or 0
                )
            ),
            1,
        )
        self.cleaned_data["salt_g"] = round(
            Decimal(
                str(data["salt"] or self.cleaned_data.get("salt_g", 0) or 0)
            ),
            1,
        )

    def clean(self) -> Dict[str, str | Decimal]:
        """Add scraped info to the fields if requested.

        Returns:
            Dict[str, str | Decimal]: cleaned data.

        Raises:
            ValidationError: if scraping is requested but URL isn't provided.
        """
        if self.cleaned_data.get("scrape_info_from_url"):
            url = self.cleaned_data.get("url")
            if not url:
                raise forms.ValidationError(
                    "URL is required to scrape the info from"
                )

            try:
                data = get_ocado_product_details(url)
            except ValueError as exc:
                raise forms.ValidationError(
                    "Only Ocado product URLs are supported"
                ) from exc

            del self.errors["name"]

            self.cleaned_data["brand"] = (
                data["brand"] or self.cleaned_data.get("brand", "") or ""
            )
            self.cleaned_data["name"] = (
                data["name"] or self.cleaned_data.get("name", "") or ""
            )
            self.cleaned_data["weight"] = round(
                Decimal(
                    str(
                        data["size"] or self.cleaned_data.get("weight", 0) or 0
                    )
                ),
                1,
            )
            self.cleaned_data["weight_unit"] = (
                data["size unit"]
                or self.cleaned_data.get("weight_unit", "g")
                or "g"
            )
            self.cleaned_data["num_servings"] = (
                data["servings"]
                or self.cleaned_data.get("num_servings", 0)
                or 0
            )
            self.cleaned_data["nutritional_info_unit"] = (
                data["size unit"]
                or self.cleaned_data.get("nutritional_info_unit", "g")
                or "g"
            )
            self._clean_nutrition_facts(data)
        elif self.cleaned_data.get("get_info_with_gemini"):
            data = get_food_nutrition_facts(self.cleaned_data["name"])
            self._clean_nutrition_facts(data)

        return self.cleaned_data


@admin.register(FoodProduct)
class FoodProductAdmin(TagsAdminMixin, admin.ModelAdmin):
    """FoodProductAdmin class."""

    # pylint: disable=duplicate-code

    form = FoodProductForm

    inlines = [
        ServingInline,
    ]

    search_fields = [
        "brand",
        "name",
        "tags__name",
    ]

    list_display = [
        "id",
        "brand",
        "name",
        "tag_list",
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
                    "tags",
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
                    "get_info_with_gemini",
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
