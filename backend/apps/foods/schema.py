"""Food Products, Servings, Recipes and Cupboard GraphQL schema module."""
import datetime

# pylint: disable=too-few-public-methods,too-many-lines

from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.foods.models import (
    CupboardItem,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)


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

    @strawberry.field
    def servings(self) -> list[ServingType]:
        """Get servings.

        Returns:
            list[ServingType]: list of servings.
        """
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
        return FoodProductType(
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return []

        return [
            FoodProductType.from_model(fp)
            for fp in FoodProduct.objects.all().order_by("name")
        ]

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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        try:
            return FoodProductType.from_model(FoodProduct.objects.get(pk=id))
        except FoodProduct.DoesNotExist:
            return None


@strawberry.type
class FoodMutation:
    """Food mutations."""

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = FoodProduct.objects.create(
            name=name,
            brand=brand,
            url=url or "",
            barcode=barcode,
            notes=notes,
            nutritional_info_size=Decimal(str(nutritional_info_size)),
            nutritional_info_unit=nutritional_info_unit,
            size=Decimal(str(size)),
            size_unit=size_unit,
            num_servings=Decimal(str(num_servings)),
            energy_kcal=Decimal(str(energy_kcal)),
            protein_g=Decimal(str(protein_g)),
            fat_g=Decimal(str(fat_g)),
            carbs_g=Decimal(str(carbs_g)),
            saturated_fat_g=(
                Decimal(str(saturated_fat_g))
                if saturated_fat_g is not None
                else None
            ),
            sugar_carbs_g=(
                Decimal(str(sugars_g)) if sugars_g is not None else None
            ),
            fibre_carbs_g=(
                Decimal(str(fibre_g)) if fibre_g is not None else None
            ),
            salt_g=Decimal(str(salt_g)) if salt_g is not None else None,
        )
        return FoodProductType.from_model(obj)

    @strawberry.mutation
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
            FoodProductType: the updated food product.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if product not found.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = FoodProduct.objects.get(pk=id)
        except FoodProduct.DoesNotExist as e:
            raise ValueError("FoodProduct not found") from e

        obj.name = name
        obj.brand = brand
        obj.url = url or ""
        obj.barcode = barcode
        obj.notes = notes
        obj.nutritional_info_size = Decimal(str(nutritional_info_size))
        obj.nutritional_info_unit = nutritional_info_unit
        obj.size = Decimal(str(size))
        obj.size_unit = size_unit
        obj.num_servings = Decimal(str(num_servings))
        obj.energy_kcal = Decimal(str(energy_kcal))
        obj.protein_g = Decimal(str(protein_g))
        obj.fat_g = Decimal(str(fat_g))
        obj.carbs_g = Decimal(str(carbs_g))
        obj.saturated_fat_g = (
            Decimal(str(saturated_fat_g))
            if saturated_fat_g is not None
            else None
        )
        obj.sugar_carbs_g = (
            Decimal(str(sugars_g)) if sugars_g is not None else None
        )
        obj.fibre_carbs_g = (
            Decimal(str(fibre_g)) if fibre_g is not None else None
        )
        obj.salt_g = Decimal(str(salt_g)) if salt_g is not None else None
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            FoodProduct.objects.get(pk=id).delete()
            return True
        except FoodProduct.DoesNotExist as e:
            raise ValueError("FoodProduct not found") from e

    @strawberry.mutation
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
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = Serving.objects.create(
            food_id=int(food_id),
            serving_size=Decimal(str(serving_size)),
            serving_unit=serving_unit,
        )
        return ServingType.from_model(obj)

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Serving.objects.get(pk=id)
            obj.serving_size = Decimal(str(serving_size))
            obj.serving_unit = serving_unit
            obj.save()
            return ServingType.from_model(obj)
        except Serving.DoesNotExist as e:
            raise ValueError("Serving not found") from e

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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

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
    food_label: str
    num_servings: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float

    @staticmethod
    def from_model(obj: RecipeIngredient) -> "RecipeIngredientType":
        """Create RecipeIngredientType from model instance.

        Args:
            obj (RecipeIngredient): model instance.

        Returns:
            RecipeIngredientType: GraphQL type.
        """
        return RecipeIngredientType(
            id=strawberry.ID(str(obj.id)),
            recipe_id=strawberry.ID(str(obj.recipe_id)),
            food_id=strawberry.ID(str(obj.food_id)),
            food_label=str(obj.food),
            num_servings=float(obj.num_servings),
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
        )


@strawberry.type
class RecipeType:
    """GraphQL Recipe Type."""

    id: strawberry.ID
    brand: str | None
    name: str
    description: str
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

    @strawberry.field
    def ingredients(self) -> list[RecipeIngredientType]:
        """Get recipe ingredients.

        Returns:
            list[RecipeIngredientType]: list of ingredients.
        """
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
        return RecipeType(
            id=strawberry.ID(str(obj.id)),
            brand=obj.brand,
            name=obj.name,
            description=obj.description,
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return []
        return [
            RecipeType.from_model(r)
            for r in Recipe.objects.all().order_by("name")
        ]

    @strawberry.field
    def recipe(self, info: Info, id: strawberry.ID) -> RecipeType | None:
        """Get a single recipe.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): recipe ID.

        Returns:
            RecipeType | None: the recipe or None.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        try:
            return RecipeType.from_model(Recipe.objects.get(pk=id))
        except Recipe.DoesNotExist:
            return None


@strawberry.type
class RecipeMutation:
    """Recipe mutations."""

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = Recipe.objects.create(
            name=name,
            brand=brand,
            description=description,
            size=Decimal(str(size)),
            size_unit=size_unit,
            num_servings=Decimal(str(num_servings)),
            energy_kcal=Decimal(str(energy_kcal)),
            protein_g=Decimal(str(protein_g)),
            fat_g=Decimal(str(fat_g)),
            carbs_g=Decimal(str(carbs_g)),
            saturated_fat_g=(
                Decimal(str(saturated_fat_g))
                if saturated_fat_g is not None
                else None
            ),
            sugar_carbs_g=(
                Decimal(str(sugars_g)) if sugars_g is not None else None
            ),
            fibre_carbs_g=(
                Decimal(str(fibre_g)) if fibre_g is not None else None
            ),
            salt_g=(Decimal(str(salt_g)) if salt_g is not None else None),
        )
        return RecipeType.from_model(obj)

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Recipe.objects.get(pk=id)
        except Recipe.DoesNotExist as e:
            raise ValueError("Recipe not found") from e

        obj.name = name
        obj.brand = brand
        obj.description = description
        obj.size = Decimal(str(size))
        obj.size_unit = size_unit
        obj.num_servings = Decimal(str(num_servings))
        obj.energy_kcal = Decimal(str(energy_kcal))
        obj.protein_g = Decimal(str(protein_g))
        obj.fat_g = Decimal(str(fat_g))
        obj.carbs_g = Decimal(str(carbs_g))
        obj.saturated_fat_g = (
            Decimal(str(saturated_fat_g))
            if saturated_fat_g is not None
            else None
        )
        obj.sugar_carbs_g = (
            Decimal(str(sugars_g)) if sugars_g is not None else None
        )
        obj.fibre_carbs_g = (
            Decimal(str(fibre_g)) if fibre_g is not None else None
        )
        obj.salt_g = Decimal(str(salt_g)) if salt_g is not None else None
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            Recipe.objects.get(pk=id).delete()
            return True
        except Recipe.DoesNotExist as e:
            raise ValueError("Recipe not found") from e

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        obj = RecipeIngredient(
            recipe_id=int(recipe_id),
            food_id=int(food_id),
            num_servings=Decimal(str(num_servings)),
        )
        obj.save()
        return RecipeIngredientType.from_model(obj)

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = RecipeIngredient.objects.get(pk=id)
        except RecipeIngredient.DoesNotExist as e:
            raise ValueError("RecipeIngredient not found") from e

        obj.food_id = int(food_id)
        obj.num_servings = Decimal(str(num_servings))
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return []
        return [
            CupboardItemType.from_model(ci)
            for ci in CupboardItem.objects.all().order_by("-purchased_at")
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        try:
            return CupboardItemType.from_model(CupboardItem.objects.get(pk=id))
        except CupboardItem.DoesNotExist:
            return None


@strawberry.type
class CupboardMutation:
    """Cupboard mutations."""

    @strawberry.mutation
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
            ValueError: if food product not found.
        """
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            food = FoodProduct.objects.get(pk=food_id)
        except FoodProduct.DoesNotExist as e:
            raise ValueError("FoodProduct not found") from e

        obj = CupboardItem.objects.create(
            food=food,
            purchased_at=datetime.datetime.fromisoformat(purchased_at),
            consumed_perc=Decimal(str(consumed_perc)),
        )
        return CupboardItemType.from_model(obj)

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = CupboardItem.objects.get(pk=id)
        except CupboardItem.DoesNotExist as e:
            raise ValueError("Item not found") from e

        obj.consumed_perc = Decimal(str(consumed_perc))
        obj.save()
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = CupboardItem.objects.get(pk=id)
            obj.delete()
            return True
        except CupboardItem.DoesNotExist as e:
            raise ValueError("Item not found") from e
