"""Food Products, Servings, Recipes and Cupboard GraphQL schema module."""

import datetime
import math
from collections.abc import Iterable
from decimal import Decimal
from typing import cast

import strawberry
from django.db import models, transaction
from django.db.models import Prefetch
from strawberry.types import Info

from apps.foods.models import (
    CupboardItem,
    Food,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)
from apps.foods.models.units import (
    UNIT_CHOICES,
    UNIT_CONTAINER,
    UNIT_SERVING,
    units_are_compatible,
)
from apps.foods.open_food_facts import (
    OpenFoodFactsProduct,
    fetch_open_food_facts_product,
    normalize_gtin,
)
from apps.foods.signals.handlers.cupboard import (
    get_linked_consumed_perc,
    recalculate_consumed_perc,
)
from apps.libs.graphql import (
    get_request_user,
    validated_decimal_field,
    validated_non_negative_decimal,
    validated_positive_decimal,
)

# pylint: disable=too-few-public-methods,too-many-lines


def _require_staff_user(info: Info) -> None:
    """Require an authenticated staff user for shared catalog writes."""
    user = get_request_user(info.context)
    if user is None or not user.is_authenticated:
        raise PermissionError("Authentication required")
    if not user.is_staff:
        raise PermissionError("Staff access required")


def _validated_unit(value: str, field_name: str) -> str:
    """Require a unit from the canonical model choices."""
    if value not in {unit for unit, _label in UNIT_CHOICES}:
        raise ValueError(f"{field_name} must be a supported unit")
    return value


def _validate_product_unit_compatibility(
    size_unit: str, nutritional_info_unit: str
) -> None:
    """Require package and nutrition bases to share a usable dimension."""
    if not units_are_compatible(size_unit, nutritional_info_unit):
        raise ValueError(
            "sizeUnit must be compatible with nutritionalInfoUnit"
        )


def _resolved_serving_unit(serving_unit: str, size_unit: str) -> str:
    """Resolve container-relative serving units to the package unit."""
    if serving_unit in {UNIT_CONTAINER, UNIT_SERVING}:
        return size_unit
    return serving_unit


def _validate_serving_unit_compatibility(
    serving_unit: str,
    size_unit: str,
    nutritional_info_unit: str,
    *,
    field_name: str = "servingUnit",
) -> None:
    """Require a serving to convert to package and nutrition dimensions."""
    resolved_unit = _resolved_serving_unit(serving_unit, size_unit)
    if not (
        units_are_compatible(resolved_unit, size_unit)
        and units_are_compatible(resolved_unit, nutritional_info_unit)
    ):
        raise ValueError(f"{field_name} must be compatible with product units")


def _validated_optional_nutrient(
    value: float | None, field_name: str, model_field: models.DecimalField
) -> Decimal | None:
    """Validate an optional finite, non-negative nutrient value."""
    if value is None:
        return None
    return validated_non_negative_decimal(value, field_name, model_field)


def _validated_nutrients(
    destination_model: type[Food],
    *,
    energy_kcal: float,
    protein_g: float,
    fat_g: float,
    carbs_g: float,
    saturated_fat_g: float | None,
    sugars_g: float | None,
    fibre_g: float | None,
    salt_g: float | None,
) -> dict[str, Decimal | None]:
    """Validate every nutrient against its destination model field."""

    def field(field_name: str) -> models.DecimalField:
        """Return a decimal destination field with a precise static type.

        Args:
            field_name: Model field name to resolve.

        Returns:
            The destination decimal field.
        """
        return cast(
            models.DecimalField,
            destination_model._meta.get_field(field_name),
        )

    return {
        "energy_kcal": validated_non_negative_decimal(
            energy_kcal, "energyKcal", field("energy_kcal")
        ),
        "protein_g": validated_non_negative_decimal(
            protein_g, "proteinG", field("protein_g")
        ),
        "fat_g": validated_non_negative_decimal(fat_g, "fatG", field("fat_g")),
        "carbs_g": validated_non_negative_decimal(
            carbs_g, "carbsG", field("carbs_g")
        ),
        "saturated_fat_g": _validated_optional_nutrient(
            saturated_fat_g, "saturatedFatG", field("saturated_fat_g")
        ),
        "sugar_carbs_g": _validated_optional_nutrient(
            sugars_g, "sugarsG", field("sugar_carbs_g")
        ),
        "fibre_carbs_g": _validated_optional_nutrient(
            fibre_g, "fibreG", field("fibre_carbs_g")
        ),
        "salt_g": _validated_optional_nutrient(
            salt_g, "saltG", field("salt_g")
        ),
    }


@strawberry.type
class ServingType:
    """GraphQL Serving Type."""

    id: strawberry.ID
    food_id: strawberry.ID
    serving_size: float
    serving_unit: str
    size: float
    size_unit: str
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float

    @staticmethod
    def from_model(obj: Serving) -> "ServingType":
        """Create ServingType from model instance.

        Args:
            obj (Serving): model instance.

        Returns:
            ServingType: GraphQL type.
        """
        return ServingType(
            id=strawberry.ID(str(obj.id)),
            food_id=strawberry.ID(str(obj.food_id)),
            serving_size=float(obj.serving_size),
            serving_unit=obj.serving_unit,
            size=float(obj.size),
            size_unit=obj.size_unit,
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
        )


@strawberry.type
class FoodProductType:
    """GraphQL FoodProduct Type."""

    id: strawberry.ID
    brand: str | None
    name: str
    url: str | None
    barcode: str | None
    notes: str
    nutritional_info_size: float
    nutritional_info_unit: str
    size: float
    size_unit: str
    num_servings: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    saturated_fat_g: float | None
    sugars_g: float | None
    fibre_g: float | None
    salt_g: float | None
    model: strawberry.Private[FoodProduct | None] = None

    @strawberry.field
    def servings(self) -> list[ServingType]:
        """Get servings.

        Returns:
            list[ServingType]: list of servings.
        """
        model = self.model
        if model is not None:
            return [ServingType.from_model(s) for s in model.servings.all()]
        return [
            ServingType.from_model(s)
            for s in Serving.objects.filter(food_id=self.id).order_by("id")
        ]

    @staticmethod
    def from_model(obj: FoodProduct) -> "FoodProductType":
        """Create FoodProductType from model.

        Args:
            obj (FoodProduct): model instance.

        Returns:
            FoodProductType: GraphQL type.
        """
        wrapped = FoodProductType(
            id=strawberry.ID(str(obj.id)),
            brand=obj.brand,
            name=obj.name,
            url=obj.url,
            barcode=obj.barcode,
            notes=obj.notes,
            nutritional_info_size=float(obj.nutritional_info_size),
            nutritional_info_unit=obj.nutritional_info_unit,
            size=float(obj.size),
            size_unit=obj.size_unit,
            num_servings=float(obj.num_servings),
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
            saturated_fat_g=(
                float(obj.saturated_fat_g)
                if obj.saturated_fat_g is not None
                else None
            ),
            sugars_g=(
                float(obj.sugar_carbs_g)
                if obj.sugar_carbs_g is not None
                else None
            ),
            fibre_g=(
                float(obj.fibre_carbs_g)
                if obj.fibre_carbs_g is not None
                else None
            ),
            salt_g=float(obj.salt_g) if obj.salt_g is not None else None,
        )
        wrapped.model = obj
        return wrapped


def _requested_field_names(info: Info) -> set[str]:
    """Return the GraphQL field names selected on the current field's type.

    Recurses into named and inline fragment selections so conditional
    hydration stays bounded for fragment-based queries too.

    Args:
        info (Info): GraphQL execution info.

    Returns:
        set[str]: names of selected fields on the current type.
    """
    names: set[str] = set()

    def _visit(selections: Iterable[object]) -> None:
        for selection in selections:
            name = getattr(selection, "name", None)
            if name:
                names.add(name)
            nested = getattr(selection, "selections", None)
            if nested:
                _visit(nested)

    for field in info.selected_fields:
        _visit(field.selections)
    return names


@strawberry.type
class OpenFoodFactsProductType:
    """GraphQL Open Food Facts product draft type."""

    barcode: str
    brand: str | None
    name: str
    url: str
    size: float
    size_unit: str
    num_servings: float
    nutritional_info_size: float
    nutritional_info_unit: str
    energy_kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    saturated_fat_g: float | None
    sugars_g: float | None
    fibre_g: float | None
    salt_g: float | None

    @staticmethod
    def from_product(
        product: OpenFoodFactsProduct,
    ) -> "OpenFoodFactsProductType":
        """Create the GraphQL draft type from a mapped OFF product.

        Args:
            product (OpenFoodFactsProduct): mapped Open Food Facts product.

        Returns:
            OpenFoodFactsProductType: GraphQL product draft.
        """
        return OpenFoodFactsProductType(
            barcode=product.barcode,
            brand=product.brand,
            name=product.name,
            url=product.url,
            size=float(product.size),
            size_unit=product.size_unit,
            num_servings=float(product.num_servings),
            nutritional_info_size=float(product.nutritional_info_size),
            nutritional_info_unit=product.nutritional_info_unit,
            energy_kcal=_optional_float(product.energy_kcal),
            protein_g=_optional_float(product.protein_g),
            fat_g=_optional_float(product.fat_g),
            carbs_g=_optional_float(product.carbs_g),
            saturated_fat_g=_optional_float(product.saturated_fat_g),
            sugars_g=_optional_float(product.sugars_g),
            fibre_g=_optional_float(product.fibre_g),
            salt_g=_optional_float(product.salt_g),
        )


@strawberry.type
class FoodProductBarcodeLookupType:
    """Food product barcode lookup result type."""

    product: FoodProductType | None
    open_food_facts: OpenFoodFactsProductType | None


def _optional_float(value: Decimal | None) -> float | None:
    """Return a decimal as a float, or None when it is absent.

    Args:
        value (Decimal | None): decimal value to convert.

    Returns:
        float | None: the converted value, or None.
    """
    return float(value) if value is not None else None


@strawberry.type
class FoodQuery:
    """Food queries."""

    @strawberry.field
    def food_products(self, info: Info) -> list[FoodProductType]:
        """Get all food products (authenticated).

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[FoodProductType]: list of food products.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []

        queryset = FoodProduct.objects.order_by("name")
        if "servings" in _requested_field_names(info):
            queryset = queryset.prefetch_related(
                Prefetch(
                    "servings",
                    queryset=Serving.objects.select_related("food").order_by(
                        "id"
                    ),
                )
            )
        return [FoodProductType.from_model(fp) for fp in queryset]

    @strawberry.field
    def food_product(
        self, info: Info, id: strawberry.ID
    ) -> FoodProductType | None:
        """Get a single food product.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): product ID.

        Returns:
            FoodProductType | None: the product or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            return FoodProductType.from_model(
                FoodProduct.objects.prefetch_related(
                    Prefetch(
                        "servings",
                        queryset=Serving.objects.select_related(
                            "food"
                        ).order_by("id"),
                    )
                ).get(pk=id)
            )
        except FoodProduct.DoesNotExist:
            return None

    @strawberry.field
    def food_product_by_barcode(
        self, info: Info, barcode: str
    ) -> FoodProductBarcodeLookupType:
        """Look up a food product by barcode, falling back to OFF.

        Local products take precedence. Unknown barcodes are looked up on
        Open Food Facts and returned as a non-persisted draft so the user
        can review it before creating a product.

        Args:
            info (Info): GraphQL execution info.
            barcode (str): scanned product barcode.

        Returns:
            FoodProductBarcodeLookupType: local product, OFF draft, or
            neither when the barcode is unknown.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return FoodProductBarcodeLookupType(
                product=None, open_food_facts=None
            )

        normalized_barcode = normalize_gtin(barcode)
        if normalized_barcode is None:
            return FoodProductBarcodeLookupType(
                product=None, open_food_facts=None
            )

        queryset = FoodProduct.objects.filter(barcode=normalized_barcode)
        if "servings" in _requested_field_names(info):
            queryset = queryset.prefetch_related(
                Prefetch(
                    "servings",
                    queryset=Serving.objects.select_related("food").order_by(
                        "id"
                    ),
                )
            )
        product = queryset.first()
        if product is not None:
            return FoodProductBarcodeLookupType(
                product=FoodProductType.from_model(product),
                open_food_facts=None,
            )

        off_product = fetch_open_food_facts_product(normalized_barcode)
        if off_product is None:
            return FoodProductBarcodeLookupType(
                product=None, open_food_facts=None
            )
        return FoodProductBarcodeLookupType(
            product=None,
            open_food_facts=OpenFoodFactsProductType.from_product(off_product),
        )


def _validated_product_num_servings(num_servings: float) -> Decimal:
    """Return a finite positive product serving count."""
    return validated_positive_decimal(
        num_servings,
        "numServings",
        FoodProduct._meta.get_field("num_servings"),
    )


def _validated_product_nutritional_info_size(
    nutritional_info_size: float,
) -> Decimal:
    """Return a finite positive product nutritional information size."""
    return validated_positive_decimal(
        nutritional_info_size,
        "nutritionalInfoSize",
        FoodProduct._meta.get_field("nutritional_info_size"),
    )


@strawberry.type
class FoodMutation:
    """Food mutations."""

    @strawberry.mutation
    @transaction.atomic
    def create_food_product(
        self,
        info: Info,
        name: str,
        brand: str | None = None,
        url: str | None = None,
        barcode: str | None = None,
        notes: str = "",
        nutritional_info_size: float = 100.0,
        nutritional_info_unit: str = "g",
        size: float = 100.0,
        size_unit: str = "g",
        num_servings: float = 1.0,
        energy_kcal: float = 0.0,
        protein_g: float = 0.0,
        fat_g: float = 0.0,
        carbs_g: float = 0.0,
        saturated_fat_g: float | None = None,
        sugars_g: float | None = None,
        fibre_g: float | None = None,
        salt_g: float | None = None,
    ) -> FoodProductType:
        """Create a new food product.

        Args:
            info (Info): GraphQL execution info.
            name (str): product name.
            brand (str | None): brand name.
            url (str | None): product URL.
            barcode (str | None): barcode.
            notes (str): additional notes.
            nutritional_info_size (float): size for nutritional info.
            nutritional_info_unit (str): unit for nutritional info.
            size (float): total size.
            size_unit (str): total size unit.
            num_servings (float): number of servings.
            energy_kcal (float): energy in kcal.
            protein_g (float): protein in g.
            fat_g (float): fat in g.
            carbs_g (float): carbs in g.
            saturated_fat_g (float | None): saturated fat in g.
            sugars_g (float | None): sugars in g.
            fibre_g (float | None): fibre in g.
            salt_g (float | None): salt in g.

        Returns:
            FoodProductType: the created food product.

        Raises:
            PermissionError: if user is not authenticated.
        """
        _require_staff_user(info)
        nutrients = _validated_nutrients(
            FoodProduct,
            energy_kcal=energy_kcal,
            protein_g=protein_g,
            fat_g=fat_g,
            carbs_g=carbs_g,
            saturated_fat_g=saturated_fat_g,
            sugars_g=sugars_g,
            fibre_g=fibre_g,
            salt_g=salt_g,
        )

        validated_nutritional_info_size = (
            _validated_product_nutritional_info_size(nutritional_info_size)
        )
        validated_nutritional_info_unit = _validated_unit(
            nutritional_info_unit, "nutritionalInfoUnit"
        )
        validated_size = validated_positive_decimal(
            size, "size", FoodProduct._meta.get_field("size")
        )
        validated_size_unit = _validated_unit(size_unit, "sizeUnit")
        validated_num_servings = _validated_product_num_servings(num_servings)
        _validate_product_unit_compatibility(
            validated_size_unit, validated_nutritional_info_unit
        )

        obj = FoodProduct.objects.create(
            name=name,
            brand=brand,
            url=url or "",
            barcode=barcode,
            notes=notes,
            nutritional_info_size=validated_nutritional_info_size,
            nutritional_info_unit=validated_nutritional_info_unit,
            size=validated_size,
            size_unit=validated_size_unit,
            num_servings=validated_num_servings,
            **nutrients,
        )
        return FoodProductType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_food_product(
        self,
        info: Info,
        id: strawberry.ID,
        name: str,
        brand: str | None = None,
        url: str | None = None,
        barcode: str | None = None,
        notes: str = "",
        nutritional_info_size: float = 100.0,
        nutritional_info_unit: str = "g",
        size: float = 100.0,
        size_unit: str = "g",
        num_servings: float = 1.0,
        energy_kcal: float = 0.0,
        protein_g: float = 0.0,
        fat_g: float = 0.0,
        carbs_g: float = 0.0,
        saturated_fat_g: float | None = None,
        sugars_g: float | None = None,
        fibre_g: float | None = None,
        salt_g: float | None = None,
    ) -> FoodProductType:
        """Update a food product.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): product ID.
            name (str): product name.
            brand (str | None): brand name.
            url (str | None): product URL; omit to preserve the current value.
            barcode (str | None): barcode.
            notes (str): additional notes.
            nutritional_info_size (float): size for nutritional info.
            nutritional_info_unit (str): unit for nutritional info.
            size (float): total size.
            size_unit (str): total size unit.
            num_servings (float): number of servings.
            energy_kcal (float): energy in kcal.
            protein_g (float): protein in g.
            fat_g (float): fat in g.
            carbs_g (float): carbs in g.
            saturated_fat_g (float | None): saturated fat in g.
            sugars_g (float | None): sugars in g.
            fibre_g (float | None): fibre in g.
            salt_g (float | None): salt in g.

        Returns:
            FoodProductType: the updated food product.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if product not found.
        """
        _require_staff_user(info)
        validated_nutritional_info_size = (
            _validated_product_nutritional_info_size(nutritional_info_size)
        )
        validated_size = validated_positive_decimal(
            size, "size", FoodProduct._meta.get_field("size")
        )
        validated_nutritional_info_unit = _validated_unit(
            nutritional_info_unit, "nutritionalInfoUnit"
        )
        validated_size_unit = _validated_unit(size_unit, "sizeUnit")
        validated_num_servings = _validated_product_num_servings(num_servings)
        _validate_product_unit_compatibility(
            validated_size_unit, validated_nutritional_info_unit
        )
        nutrients = _validated_nutrients(
            FoodProduct,
            energy_kcal=energy_kcal,
            protein_g=protein_g,
            fat_g=fat_g,
            carbs_g=carbs_g,
            saturated_fat_g=saturated_fat_g,
            sugars_g=sugars_g,
            fibre_g=fibre_g,
            salt_g=salt_g,
        )

        try:
            obj = FoodProduct.objects.get(pk=id)
        except FoodProduct.DoesNotExist as e:
            raise ValueError("FoodProduct not found") from e

        for existing_serving_unit in obj.servings.values_list(
            "serving_unit", flat=True
        ):
            _validate_serving_unit_compatibility(
                existing_serving_unit,
                validated_size_unit,
                validated_nutritional_info_unit,
                field_name="Existing servingUnit",
            )

        obj.name = name
        obj.brand = brand
        if url is not None:
            obj.url = url
        obj.barcode = barcode
        obj.notes = notes
        obj.nutritional_info_size = validated_nutritional_info_size
        obj.nutritional_info_unit = validated_nutritional_info_unit
        obj.size = validated_size
        obj.size_unit = validated_size_unit
        obj.num_servings = validated_num_servings
        for nutrient_name, nutrient_value in nutrients.items():
            setattr(obj, nutrient_name, nutrient_value)
        obj.save()
        return FoodProductType.from_model(obj)

    @strawberry.mutation
    def delete_food_product(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a food product.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): product ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if product not found.
        """
        _require_staff_user(info)

        try:
            FoodProduct.objects.get(pk=id).delete()
            return True
        except FoodProduct.DoesNotExist as e:
            raise ValueError("FoodProduct not found") from e

    @strawberry.mutation
    @transaction.atomic
    def create_serving(
        self,
        info: Info,
        food_id: strawberry.ID,
        serving_size: float,
        serving_unit: str,
    ) -> ServingType:
        """Create a new serving size.

        Args:
            info (Info): GraphQL execution info.
            food_id (strawberry.ID): food product ID.
            serving_size (float): size value.
            serving_unit (str): size unit.

        Returns:
            ServingType: the created serving.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if the food is missing or units are incompatible.
        """
        _require_staff_user(info)
        validated_serving_size = validated_positive_decimal(
            serving_size,
            "servingSize",
            Serving._meta.get_field("serving_size"),
        )
        validated_serving_unit = _validated_unit(serving_unit, "servingUnit")
        try:
            food = Food.objects.get(pk=food_id)
        except Food.DoesNotExist as e:
            raise ValueError("Food not found") from e
        _validate_serving_unit_compatibility(
            validated_serving_unit,
            food.size_unit,
            food.nutritional_info_unit,
        )

        obj = Serving.objects.create(
            food=food,
            serving_size=validated_serving_size,
            serving_unit=validated_serving_unit,
        )
        return ServingType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_serving(
        self,
        info: Info,
        id: strawberry.ID,
        serving_size: float,
        serving_unit: str,
    ) -> ServingType:
        """Update an existing serving size.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): serving ID.
            serving_size (float): size value.
            serving_unit (str): size unit.

        Returns:
            ServingType: the updated serving.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if serving not found.
        """
        _require_staff_user(info)
        validated_serving_size = validated_positive_decimal(
            serving_size,
            "servingSize",
            Serving._meta.get_field("serving_size"),
        )
        validated_serving_unit = _validated_unit(serving_unit, "servingUnit")

        try:
            obj = Serving.objects.select_related("food").get(pk=id)
        except Serving.DoesNotExist as e:
            raise ValueError("Serving not found") from e

        _validate_serving_unit_compatibility(
            validated_serving_unit,
            obj.food.size_unit,
            obj.food.nutritional_info_unit,
        )
        obj.serving_size = validated_serving_size
        obj.serving_unit = validated_serving_unit
        obj.save()
        return ServingType.from_model(obj)

    @strawberry.mutation
    def delete_serving(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a serving size.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): serving ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if serving not found.
        """
        _require_staff_user(info)

        try:
            Serving.objects.get(pk=id).delete()
            return True
        except Serving.DoesNotExist as e:
            raise ValueError("Serving not found") from e


@strawberry.type
class RecipeIngredientType:
    """GraphQL RecipeIngredient Type."""

    id: strawberry.ID
    recipe_id: strawberry.ID
    food_id: strawberry.ID
    num_servings: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    model: strawberry.Private[RecipeIngredient | None] = None

    @staticmethod
    def from_model(obj: RecipeIngredient) -> "RecipeIngredientType":
        """Create RecipeIngredientType from model instance.

        Args:
            obj (RecipeIngredient): model instance.

        Returns:
            RecipeIngredientType: GraphQL type.
        """
        wrapped = RecipeIngredientType(
            id=strawberry.ID(str(obj.id)),
            recipe_id=strawberry.ID(str(obj.recipe_id)),
            food_id=strawberry.ID(str(obj.food_id)),
            num_servings=float(obj.num_servings),
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
        )
        wrapped.model = obj
        return wrapped

    @strawberry.field
    def food_label(self) -> str:
        """Resolve ingredient label lazily to avoid eager food loading.

        Returns:
            str: human-readable label.
        """
        model = self.model
        if model is None:
            return ""
        return str(model.food)


@strawberry.type
class RecipeType:
    """GraphQL Recipe Type."""

    id: strawberry.ID
    brand: str | None
    name: str
    description: str
    nutrients_from_ingredients: bool
    size: float
    size_unit: str
    num_servings: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    saturated_fat_g: float | None
    sugars_g: float | None
    fibre_g: float | None
    salt_g: float | None
    model: strawberry.Private[Recipe | None] = None

    @strawberry.field
    def ingredients(self) -> list[RecipeIngredientType]:
        """Get recipe ingredients.

        Returns:
            list[RecipeIngredientType]: list of ingredients.
        """
        model = self.model
        if model is not None:
            return [
                RecipeIngredientType.from_model(i)
                for i in model.ingredients.all()
            ]
        return [
            RecipeIngredientType.from_model(i)
            for i in RecipeIngredient.objects.filter(
                recipe_id=self.id
            ).order_by("id")
        ]

    @staticmethod
    def from_model(obj: Recipe) -> "RecipeType":
        """Create RecipeType from model.

        Args:
            obj (Recipe): model instance.

        Returns:
            RecipeType: GraphQL type.
        """
        wrapped = RecipeType(
            id=strawberry.ID(str(obj.id)),
            brand=obj.brand,
            name=obj.name,
            description=obj.description,
            nutrients_from_ingredients=obj.nutrients_from_ingredients,
            size=float(obj.size),
            size_unit=obj.size_unit,
            num_servings=float(obj.num_servings),
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
            saturated_fat_g=(
                float(obj.saturated_fat_g)
                if obj.saturated_fat_g is not None
                else None
            ),
            sugars_g=(
                float(obj.sugar_carbs_g)
                if obj.sugar_carbs_g is not None
                else None
            ),
            fibre_g=(
                float(obj.fibre_carbs_g)
                if obj.fibre_carbs_g is not None
                else None
            ),
            salt_g=float(obj.salt_g) if obj.salt_g is not None else None,
        )
        wrapped.model = obj
        return wrapped


@strawberry.type
class RecipeQuery:
    """Recipe queries."""

    @strawberry.field
    def recipes(self, info: Info) -> list[RecipeType]:
        """Retrieve all recipes for the authenticated user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[RecipeType]: list of recipes.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []
        queryset = Recipe.objects.order_by("name")
        if "ingredients" in _requested_field_names(info):
            queryset = queryset.prefetch_related(
                Prefetch(
                    "ingredients",
                    queryset=RecipeIngredient.objects.select_related(
                        "food__food"
                    ).order_by("id"),
                )
            )
        return [RecipeType.from_model(r) for r in queryset]

    @strawberry.field
    def recipe(self, info: Info, id: strawberry.ID) -> RecipeType | None:
        """Get a single recipe.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): recipe ID.

        Returns:
            RecipeType | None: the recipe or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None
        try:
            return RecipeType.from_model(
                Recipe.objects.prefetch_related(
                    Prefetch(
                        "ingredients",
                        queryset=RecipeIngredient.objects.select_related(
                            "food__food"
                        ).order_by("id"),
                    ),
                ).get(pk=id)
            )
        except Recipe.DoesNotExist:
            return None


def _validated_recipe_num_servings(num_servings: float) -> Decimal:
    """Return a valid positive recipe serving count."""
    return validated_positive_decimal(
        num_servings,
        "numServings",
        Recipe._meta.get_field("num_servings"),
    )


def _validated_ingredient_num_servings(num_servings: float) -> Decimal:
    """Validate positivity and the model field's persisted decimal precision."""
    return validated_positive_decimal(
        num_servings,
        "numServings",
        RecipeIngredient._meta.get_field("num_servings"),
    )


@strawberry.type
class RecipeMutation:
    """Recipe mutations."""

    @strawberry.mutation
    @transaction.atomic
    def create_recipe(
        self,
        info: Info,
        name: str,
        brand: str | None = None,
        description: str = "",
        size: float = 100.0,
        size_unit: str = "g",
        num_servings: float = 1.0,
        energy_kcal: float = 0.0,
        protein_g: float = 0.0,
        fat_g: float = 0.0,
        carbs_g: float = 0.0,
        saturated_fat_g: float | None = None,
        sugars_g: float | None = None,
        fibre_g: float | None = None,
        salt_g: float | None = None,
    ) -> RecipeType:
        """Create a new recipe.

        Args:
            info (Info): GraphQL execution info.
            name (str): recipe name.
            brand (str | None): brand name.
            description (str): recipe description.
            size (float): total size.
            size_unit (str): total size unit.
            num_servings (float): number of servings.
            energy_kcal (float): energy in kcal.
            protein_g (float): protein in g.
            fat_g (float): fat in g.
            carbs_g (float): carbs in g.
            saturated_fat_g (float | None): saturated fat in g.
            sugars_g (float | None): sugars in g.
            fibre_g (float | None): fibre in g.
            salt_g (float | None): salt in g.

        Returns:
            RecipeType: the created recipe.

        Raises:
            PermissionError: if user is not authenticated.
        """
        _require_staff_user(info)
        nutrients = _validated_nutrients(
            Recipe,
            energy_kcal=energy_kcal,
            protein_g=protein_g,
            fat_g=fat_g,
            carbs_g=carbs_g,
            saturated_fat_g=saturated_fat_g,
            sugars_g=sugars_g,
            fibre_g=fibre_g,
            salt_g=salt_g,
        )
        validated_size_unit = _validated_unit(size_unit, "sizeUnit")

        obj = Recipe.objects.create(
            name=name,
            brand=brand,
            description=description,
            size=validated_positive_decimal(
                size, "size", Recipe._meta.get_field("size")
            ),
            size_unit=validated_size_unit,
            nutritional_info_unit=validated_size_unit,
            num_servings=_validated_recipe_num_servings(num_servings),
            **nutrients,
        )
        return RecipeType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_recipe(
        self,
        info: Info,
        id: strawberry.ID,
        name: str,
        brand: str | None = None,
        description: str = "",
        size: float = 100.0,
        size_unit: str = "g",
        num_servings: float = 1.0,
        energy_kcal: float = 0.0,
        protein_g: float = 0.0,
        fat_g: float = 0.0,
        carbs_g: float = 0.0,
        saturated_fat_g: float | None = None,
        sugars_g: float | None = None,
        fibre_g: float | None = None,
        salt_g: float | None = None,
    ) -> RecipeType:
        """Update a recipe.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): recipe ID.
            name (str): recipe name.
            brand (str | None): brand name.
            description (str): recipe description.
            size (float): total size.
            size_unit (str): total size unit.
            num_servings (float): number of servings.
            energy_kcal (float): energy in kcal.
            protein_g (float): protein in g.
            fat_g (float): fat in g.
            carbs_g (float): carbs in g.
            saturated_fat_g (float | None): saturated fat in g.
            sugars_g (float | None): sugars in g.
            fibre_g (float | None): fibre in g.
            salt_g (float | None): salt in g.

        Returns:
            RecipeType: the updated recipe.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if recipe not found.
        """
        _require_staff_user(info)
        try:
            obj = Recipe.objects.select_for_update().get(pk=id)
        except Recipe.DoesNotExist as e:
            raise ValueError("Recipe not found") from e

        validated_num_servings = _validated_recipe_num_servings(num_servings)
        obj.name = name
        obj.brand = brand
        obj.description = description
        obj.num_servings = validated_num_servings

        if not obj.nutrients_from_ingredients:
            validated_size = validated_positive_decimal(
                size, "size", Recipe._meta.get_field("size")
            )
            validated_size_unit = _validated_unit(size_unit, "sizeUnit")
            nutrients = _validated_nutrients(
                Recipe,
                energy_kcal=energy_kcal,
                protein_g=protein_g,
                fat_g=fat_g,
                carbs_g=carbs_g,
                saturated_fat_g=saturated_fat_g,
                sugars_g=sugars_g,
                fibre_g=fibre_g,
                salt_g=salt_g,
            )
            obj.size = validated_size
            obj.size_unit = validated_size_unit
            obj.nutritional_info_unit = validated_size_unit
            for nutrient_name, nutrient_value in nutrients.items():
                setattr(obj, nutrient_name, nutrient_value)

        obj.save()
        return RecipeType.from_model(obj)

    @strawberry.mutation
    def delete_recipe(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a recipe.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): recipe ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if recipe not found.
        """
        _require_staff_user(info)

        try:
            Recipe.objects.get(pk=id).delete()
            return True
        except Recipe.DoesNotExist as e:
            raise ValueError("Recipe not found") from e

    @strawberry.mutation
    @transaction.atomic
    def add_recipe_ingredient(
        self,
        info: Info,
        recipe_id: strawberry.ID,
        food_id: strawberry.ID,
        num_servings: float = 1.0,
    ) -> RecipeIngredientType:
        """Add an ingredient to a recipe.

        Args:
            info (Info): GraphQL execution info.
            recipe_id (strawberry.ID): recipe ID.
            food_id (strawberry.ID): food product ID.
            num_servings (float): number of servings.

        Returns:
            RecipeIngredientType: the added ingredient.

        Raises:
            PermissionError: if user is not authenticated.
        """
        _require_staff_user(info)

        obj = RecipeIngredient(
            recipe_id=int(recipe_id),
            food_id=int(food_id),
            num_servings=_validated_ingredient_num_servings(num_servings),
        )
        obj.save()
        return RecipeIngredientType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_recipe_ingredient(
        self,
        info: Info,
        id: strawberry.ID,
        food_id: strawberry.ID,
        num_servings: float = 1.0,
    ) -> RecipeIngredientType:
        """Update a recipe ingredient.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): ingredient ID.
            food_id (strawberry.ID): food product ID.
            num_servings (float): number of servings.

        Returns:
            RecipeIngredientType: the updated ingredient.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if ingredient not found.
        """
        _require_staff_user(info)
        validated_num_servings = _validated_ingredient_num_servings(
            num_servings
        )

        try:
            obj = RecipeIngredient.objects.get(pk=id)
        except RecipeIngredient.DoesNotExist as e:
            raise ValueError("RecipeIngredient not found") from e

        obj.food_id = int(food_id)
        obj.num_servings = validated_num_servings
        obj.save()
        return RecipeIngredientType.from_model(obj)

    @strawberry.mutation
    def delete_recipe_ingredient(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a recipe ingredient.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): ingredient ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if ingredient not found.
        """
        _require_staff_user(info)

        try:
            RecipeIngredient.objects.get(pk=id).delete()
            return True
        except RecipeIngredient.DoesNotExist as e:
            raise ValueError("RecipeIngredient not found") from e


@strawberry.type
class CupboardItemType:
    """GraphQL CupboardItem Type."""

    id: strawberry.ID
    food_id: strawberry.ID
    food_label: str
    started: bool
    finished: bool
    purchased_at: str
    consumed_perc: float
    consumed_servings: float
    remaining_servings: float

    @staticmethod
    def from_model(obj: CupboardItem) -> "CupboardItemType":
        """Create CupboardItemType from model instance.

        Args:
            obj (CupboardItem): model instance.

        Returns:
            CupboardItemType: GraphQL type.
        """
        return CupboardItemType(
            id=strawberry.ID(str(obj.id)),
            food_id=strawberry.ID(str(obj.food_id)),
            food_label=str(obj),
            started=obj.started,
            finished=obj.finished,
            purchased_at=obj.purchased_at.isoformat(),
            consumed_perc=float(obj.consumed_perc),
            consumed_servings=float(obj.consumed_servings),
            remaining_servings=float(obj.remaining_servings),
        )


def _validated_consumed_perc(consumed_perc: float) -> Decimal:
    """Return a valid cupboard consumption percentage.

    Args:
        consumed_perc (float): consumed percentage.

    Returns:
        Decimal: validated percentage.

    Raises:
        ValueError: if the percentage is outside zero to one hundred.
    """
    if not math.isfinite(consumed_perc) or not 0 <= consumed_perc <= 100:
        raise ValueError("consumedPerc must be between 0 and 100")
    return validated_decimal_field(
        Decimal(str(consumed_perc)),
        "consumedPerc",
        CupboardItem._meta.get_field("consumed_perc"),
    )


@strawberry.type
class CupboardQuery:
    """Cupboard queries."""

    @strawberry.field
    def cupboard_items(self, info: Info) -> list[CupboardItemType]:
        """Get all cupboard items (authenticated).

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[CupboardItemType]: list of cupboard items.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []
        return [
            CupboardItemType.from_model(ci)
            for ci in CupboardItem.objects.filter(owner=user).order_by(
                "-purchased_at"
            )
        ]

    @strawberry.field
    def cupboard_item(
        self, info: Info, id: strawberry.ID
    ) -> CupboardItemType | None:
        """Get a single cupboard item.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): item ID.

        Returns:
            CupboardItemType | None: the item or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None
        try:
            return CupboardItemType.from_model(
                CupboardItem.objects.get(pk=id, owner=user)
            )
        except CupboardItem.DoesNotExist:
            return None


@strawberry.type
class CupboardMutation:
    """Cupboard mutations."""

    @strawberry.mutation
    @transaction.atomic
    def create_cupboard_item(
        self,
        info: Info,
        food_id: strawberry.ID,
        purchased_at: str,
        consumed_perc: float = 0.0,
    ) -> CupboardItemType:
        """Create a new cupboard item.

        Args:
            info (Info): GraphQL execution info.
            food_id (strawberry.ID): food product ID.
            purchased_at (str): purchase date in ISO format.
            consumed_perc (float): consumed percentage.

        Returns:
            CupboardItemType: the created cupboard item.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if food not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            food = Food.objects.get(pk=food_id)
        except Food.DoesNotExist as e:
            raise ValueError("Food not found") from e

        obj = CupboardItem.objects.create(
            owner=user,
            food=food,
            purchased_at=datetime.datetime.fromisoformat(purchased_at),
            consumed_perc=_validated_consumed_perc(consumed_perc),
        )
        return CupboardItemType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_cupboard_item(
        self,
        info: Info,
        id: strawberry.ID,
        consumed_perc: float,
    ) -> CupboardItemType:
        """Update a cupboard item.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): cupboard item ID.
            consumed_perc (float): consumed percentage.

        Returns:
            CupboardItemType: the updated cupboard item.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if item not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = (
                CupboardItem.objects.select_for_update()
                .select_related("food")
                .get(pk=id, owner=user)
            )
        except CupboardItem.DoesNotExist as e:
            raise ValueError("Item not found") from e

        requested_total = _validated_consumed_perc(consumed_perc)
        linked_consumed_perc = get_linked_consumed_perc(obj)
        if requested_total < linked_consumed_perc:
            raise ValueError(
                "consumedPerc cannot be less than linked consumption"
            )
        obj.manual_consumed_perc = requested_total - linked_consumed_perc
        CupboardItem.objects.filter(pk=obj.pk).update(
            manual_consumed_perc=obj.manual_consumed_perc
        )
        recalculate_consumed_perc(obj, already_locked=True)
        return CupboardItemType.from_model(obj)

    @strawberry.mutation
    def delete_cupboard_item(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a cupboard item.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): item ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if item not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = CupboardItem.objects.get(pk=id, owner=user)
            obj.delete()
            return True
        except CupboardItem.DoesNotExist as e:
            raise ValueError("Item not found") from e
