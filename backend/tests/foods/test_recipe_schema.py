"""Tests for Recipes GraphQL schema."""

# The complete recipe GraphQL contract is intentionally exercised together.
# pylint: disable=too-many-lines

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.foods.models import FoodProduct, Recipe, RecipeIngredient
from config.schema import schema

User = get_user_model()


def _create_user(email, *, is_staff=False):
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
        is_staff=is_staff,
    )


@pytest.mark.django_db
class TestRecipeQuery:
    """Tests for recipe queries."""

    def _count_recipes_with_ingredient_query(
        self, mocker, recipe_count: int
    ) -> int:
        """Create recipes and count SQL queries for nested ingredients."""
        user = _create_user(f"rq-query-{recipe_count}-bounded@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        product = FoodProduct.objects.create(
            name="Ingredient",
            size=100,
            size_unit="g",
            num_servings=1,
            nutritional_info_size=100,
            nutritional_info_unit="g",
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")

        for index in range(recipe_count):
            recipe = Recipe.objects.create(
                name=f"Recipe {index}",
                size=100,
                size_unit="g",
                num_servings=1,
            )
            RecipeIngredient.objects.create(
                recipe=recipe,
                food=serving,
                num_servings=1,
            )

        query = "{ recipes { id name ingredients { id } } }"
        with CaptureQueriesContext(connection) as captured:
            result = schema.execute_sync(query, context_value=mock_context)

        assert result.errors is None
        return len(captured)

    def test_recipes_query(self, mocker):
        """Test listing recipes."""
        # Given an authenticated user and some recipes
        user = _create_user("rq@test.com")
        Recipe.objects.create(
            name="Omelette", size=200, size_unit="g", num_servings=1
        )
        Recipe.objects.create(
            name="Smoothie", size=500, size_unit="ml", num_servings=2
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When querying all recipes
        query = "{ recipes { id name } }"
        result = schema.execute_sync(query, context_value=mock_context)

        # Then the result contains both recipes ordered by name
        assert result.errors is None
        assert len(result.data["recipes"]) == 2
        assert result.data["recipes"][0]["name"] == "Omelette"
        assert result.data["recipes"][1]["name"] == "Smoothie"

    def test_recipes_query_with_ingredients_has_bounded_query_growth(
        self, mocker
    ):
        """Nested ingredient queries stop increasing with more recipes."""
        base_queries = self._count_recipes_with_ingredient_query(mocker, 2)
        growth_queries = self._count_recipes_with_ingredient_query(mocker, 10)

        assert growth_queries == base_queries

    def test_recipe_detail_query(self, mocker):
        """Test getting a single recipe."""
        # Given an authenticated user and a recipe
        user = _create_user("rd@test.com")
        recipe = Recipe.objects.create(
            name="Pasta",
            description="Yummy",
            size=400,
            size_unit="g",
            num_servings=2,
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When querying the recipe by id
        query = """
            query GetRecipe($id: ID!) {
                recipe(id: $id) { name description }
            }
        """
        result = schema.execute_sync(
            query,
            variable_values={"id": str(recipe.id)},
            context_value=mock_context,
        )

        # Then the result contains the recipe
        assert result.errors is None
        assert result.data["recipe"]["name"] == "Pasta"
        assert result.data["recipe"]["description"] == "Yummy"

    def test_recipe_detail_query_exposes_ingredient_derived_mode(self, mocker):
        """Recipe responses include the persisted aggregate source mode."""
        user = _create_user("recipe-mode@test.com")
        recipe = Recipe.objects.create(
            name="Ingredient-derived",
            nutrients_from_ingredients=True,
            size=0,
        )
        context = mocker.Mock()
        context.request.user = user

        result = schema.execute_sync(
            """
                query GetRecipeMode($id: ID!) {
                    recipe(id: $id) { nutrientsFromIngredients }
                }
            """,
            variable_values={"id": str(recipe.id)},
            context_value=context,
        )

        assert result.errors is None
        assert result.data["recipe"]["nutrientsFromIngredients"] is True


@pytest.mark.django_db
class TestRecipeMutation:  # pylint: disable=too-many-public-methods
    """Tests for recipe mutations."""

    def test_create_recipe(self, mocker):
        """Test creating a recipe."""
        # Given an authenticated user
        user = _create_user("rc@test.com", is_staff=True)

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When creating a recipe
        mutation = """
            mutation CreateRecipe($name: String!, $energyKcal: Float!) {
                createRecipe(name: $name, energyKcal: $energyKcal) { id name }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"name": "Porridge", "energyKcal": 350.0},
            context_value=mock_context,
        )

        # Then the recipe is created
        assert result.errors is None
        assert result.data["createRecipe"]["name"] == "Porridge"
        assert Recipe.objects.filter(name="Porridge").exists()

    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_recipe_accepts_representable_decimal_boundaries(
        self, mocker, operation
    ):
        """Both recipe write paths preserve supported one/two-decimal values."""
        user = _create_user(
            f"recipe-boundary-{operation}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(name="Original")
        arguments = """
            name: "Boundary", size: 99.9, sizeUnit: "g", numServings: 0.1,
            energyKcal: 12.34, proteinG: 23.45, fatG: 34.56,
            carbsG: 45.67, saturatedFatG: 1.23, sugarsG: 2.34,
            fibreG: 3.45, saltG: null
        """
        if operation == "create":
            mutation = f"mutation {{ createRecipe({arguments}) {{ id }} }}"
        else:
            mutation = f"""
                mutation UpdateBoundary($id: ID!) {{
                    updateRecipe(id: $id, {arguments}) {{ id }}
                }}
            """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(recipe.id)},
            context_value=context,
        )

        assert result.errors is None
        persisted = Recipe.objects.get(
            pk=result.data[
                "createRecipe" if operation == "create" else "updateRecipe"
            ]["id"]
        )
        assert (
            persisted.size,
            persisted.num_servings,
            persisted.energy_kcal,
            persisted.protein_g,
            persisted.fat_g,
            persisted.carbs_g,
            persisted.saturated_fat_g,
            persisted.sugar_carbs_g,
            persisted.fibre_carbs_g,
            persisted.salt_g,
        ) == (
            Decimal("99.9"),
            Decimal("0.1"),
            Decimal("12.34"),
            Decimal("23.45"),
            Decimal("34.56"),
            Decimal("45.67"),
            Decimal("1.23"),
            Decimal("2.34"),
            Decimal("3.45"),
            None,
        )

    def test_create_recipe_rejects_non_staff_user(self, mocker):
        """A regular user cannot create a shared recipe."""
        user = _create_user("rc-regular@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            'mutation { createRecipe(name: "Shared") { id } }',
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert not Recipe.objects.filter(name="Shared").exists()

    def test_update_recipe(self, mocker):
        """Test updating a recipe."""
        # Given an authenticated user and a recipe
        user = _create_user("ru@test.com", is_staff=True)
        recipe = Recipe.objects.create(
            name="Old Name", size=100, size_unit="g", num_servings=1
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When updating the recipe
        mutation = """
            mutation UpdateRecipe($id: ID!, $name: String!) {
                updateRecipe(id: $id, name: $name, energyKcal: 200.0) { name }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(recipe.id), "name": "New Name"},
            context_value=mock_context,
        )

        # Then the recipe is updated
        assert result.errors is None
        assert result.data["updateRecipe"]["name"] == "New Name"

    def test_update_empty_derived_recipe_ignores_client_aggregates(
        self, mocker
    ):
        """Metadata edits preserve authoritative zero totals for empty recipes."""
        user = _create_user("derived-update@test.com", is_staff=True)
        recipe = Recipe.objects.create(
            name="Empty derived",
            description="Before",
            nutrients_from_ingredients=True,
            size=0,
            size_unit="g",
            nutritional_info_unit="g",
            num_servings=1,
        )
        context = mocker.Mock()
        context.request.user = user

        result = schema.execute_sync(
            """
                mutation UpdateDerivedRecipe($id: ID!) {
                    updateRecipe(
                        id: $id,
                        name: "Renamed derived",
                        brand: "Updated brand",
                        description: "After",
                        size: 0,
                        sizeUnit: "unsupported-client-unit",
                        numServings: 2,
                        energyKcal: 999,
                        proteinG: 999,
                        fatG: 999,
                        carbsG: 999,
                        saturatedFatG: 999,
                        sugarsG: 999,
                        fibreG: 999,
                        saltG: 999
                    ) {
                        name size sizeUnit numServings energyKcal
                    }
                }
            """,
            variable_values={"id": str(recipe.id)},
            context_value=context,
        )

        assert result.errors is None
        assert result.data["updateRecipe"] == {
            "name": "Renamed derived",
            "size": 0.0,
            "sizeUnit": "g",
            "numServings": 2.0,
            "energyKcal": 0.0,
        }
        recipe.refresh_from_db()
        assert (recipe.brand, recipe.description) == ("Updated brand", "After")
        assert (
            recipe.size,
            recipe.size_unit,
            recipe.nutritional_info_unit,
            recipe.energy_kcal,
            recipe.protein_g,
            recipe.fat_g,
            recipe.carbs_g,
            recipe.saturated_fat_g,
            recipe.sugar_carbs_g,
            recipe.fibre_carbs_g,
            recipe.salt_g,
        ) == (
            Decimal("0"),
            "g",
            "g",
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        )

    def test_update_recipe_rejects_non_staff_user(self, mocker):
        """A regular user cannot update a shared recipe."""
        user = _create_user("ru-regular@test.com")
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateRecipe($id: ID!) {
                updateRecipe(id: $id, name: "Changed") { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(recipe.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        recipe.refresh_from_db()
        assert recipe.name == "Shared"

    @pytest.mark.parametrize(
        "size",
        [
            0.0,
            0.01,
            1000000000.0,
            -1.0,
            float("nan"),
            float("inf"),
            -float("inf"),
        ],
    )
    def test_create_recipe_rejects_invalid_size_without_persisting(
        self, mocker, size
    ):
        """Creating a recipe requires a finite positive size."""
        user = _create_user(f"rc-size-{repr(size)}@example.com", is_staff=True)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateRecipe($size: Float!) {
                createRecipe(name: "Invalid size", size: $size) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"size": size},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert not Recipe.objects.filter(name="Invalid size").exists()

    @pytest.mark.parametrize(
        ("num_servings", "error"),
        [
            (0.0, "numServings must be greater than 0"),
            (-1.0, "numServings must be greater than 0"),
            (0.01, "numServings exceeds supported precision"),
            (1000000000.0, "numServings exceeds supported precision"),
        ],
    )
    def test_create_recipe_rejects_invalid_serving_count(
        self, mocker, num_servings, error
    ):
        """Creating a recipe requires a positive, representable serving count."""
        user = _create_user(
            f"rc-invalid-{num_servings}@test.com", is_staff=True
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateRecipe($numServings: Float!) {
                createRecipe(
                    name: "Invalid", numServings: $numServings,
                    energyKcal: 100.0
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"numServings": num_servings},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert error in str(result.errors[0])
        assert not Recipe.objects.filter(name="Invalid").exists()

    @pytest.mark.parametrize(
        "size",
        [
            0.0,
            0.01,
            1000000000.0,
            -1.0,
            float("nan"),
            float("inf"),
            -float("inf"),
        ],
    )
    def test_update_recipe_rejects_invalid_size_without_partial_writes(
        self, mocker, size
    ):
        """Invalid recipe sizes leave every persisted field unchanged."""
        user = _create_user(f"ru-size-{repr(size)}@example.com", is_staff=True)
        recipe = Recipe.objects.create(
            name="Valid",
            brand="Original",
            description="Unchanged",
            size=100,
            size_unit="g",
            num_servings=1,
            energy_kcal=200,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateRecipe($id: ID!, $size: Float!) {
                updateRecipe(
                    id: $id, name: "Invalid", brand: "Changed",
                    description: "Changed", size: $size, sizeUnit: "ml",
                    numServings: 2, energyKcal: 999
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(recipe.id), "size": size},
            context_value=mock_context,
        )

        assert result.errors is not None
        recipe.refresh_from_db()
        assert (
            recipe.name,
            recipe.brand,
            recipe.description,
            recipe.size,
            recipe.size_unit,
            recipe.num_servings,
            recipe.energy_kcal,
        ) == (
            "Valid",
            "Original",
            "Unchanged",
            100,
            "g",
            1,
            200,
        )

    @pytest.mark.parametrize(
        ("num_servings", "error"),
        [
            (0.0, "numServings must be greater than 0"),
            (-1.0, "numServings must be greater than 0"),
            (0.01, "numServings exceeds supported precision"),
            (1000000000.0, "numServings exceeds supported precision"),
        ],
    )
    def test_update_recipe_rejects_invalid_serving_count(
        self, mocker, num_servings, error
    ):
        """Updating a recipe requires a positive, representable serving count."""
        user = _create_user(
            f"ru-invalid-{num_servings}@test.com", is_staff=True
        )
        recipe = Recipe.objects.create(
            name="Valid", size=100, size_unit="g", num_servings=1
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateRecipe($id: ID!, $numServings: Float!) {
                updateRecipe(
                    id: $id, name: "Invalid",
                    numServings: $numServings, energyKcal: 100.0
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(recipe.id),
                "numServings": num_servings,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        assert error in str(result.errors[0])
        recipe.refresh_from_db()
        assert recipe.name == "Valid"
        assert recipe.num_servings == 1

    @pytest.mark.parametrize("operation", ["create", "update"])
    @pytest.mark.parametrize(
        "field_name",
        [
            "energyKcal",
            "proteinG",
            "fatG",
            "carbsG",
            "saturatedFatG",
            "sugarsG",
            "fibreG",
            "saltG",
        ],
    )
    @pytest.mark.parametrize(
        "value", [-0.1, 0.001, 100000000.0, float("nan"), float("inf")]
    )
    def test_recipe_rejects_invalid_nutrients_without_partial_writes(
        self, mocker, operation, field_name, value
    ):
        """Every exposed recipe nutrient is finite and non-negative."""
        user = _create_user(
            f"recipe-nutrient-{operation}-{field_name}-{repr(value)}@test.com",
            is_staff=True,
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Original recipe nutrients",
            energy_kcal=100,
            protein_g=10,
            fat_g=5,
            carbs_g=15,
            saturated_fat_g=2,
            sugar_carbs_g=3,
            fibre_carbs_g=4,
            salt_g=1,
        )
        original_count = Recipe.objects.count()
        nutrient_fields = (
            "name",
            "energy_kcal",
            "protein_g",
            "fat_g",
            "carbs_g",
            "saturated_fat_g",
            "sugar_carbs_g",
            "fibre_carbs_g",
            "salt_g",
        )
        original_state = tuple(
            getattr(recipe, field) for field in nutrient_fields
        )
        original_servings = list(
            recipe.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        if operation == "create":
            mutation = f"""
                mutation InvalidNutrient($value: Float!) {{
                    createRecipe(
                        name: "Invalid recipe nutrient", {field_name}: $value
                    ) {{ id }}
                }}
            """
            variables = {"value": value}
        else:
            mutation = f"""
                mutation InvalidNutrient($id: ID!, $value: Float!) {{
                    updateRecipe(
                        id: $id, name: "Changed", {field_name}: $value
                    ) {{ id }}
                }}
            """
            variables = {"id": str(recipe.id), "value": value}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        if value == -0.1:
            assert f"{field_name} must be greater than or equal to 0" in str(
                result.errors[0]
            )
        assert Recipe.objects.count() == original_count
        recipe.refresh_from_db()
        assert (
            tuple(getattr(recipe, field) for field in nutrient_fields)
            == original_state
        )
        assert (
            list(
                recipe.servings.order_by("id").values_list(
                    "id", "serving_size", "serving_unit", "energy_kcal"
                )
            )
            == original_servings
        )

    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_recipe_rejects_unsupported_size_unit_without_partial_writes(
        self, mocker, operation
    ):
        """Recipe size units must come from the canonical model choices."""
        user = _create_user(f"recipe-unit-{operation}@test.com", is_staff=True)
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(name="Original recipe unit")
        original_count = Recipe.objects.count()
        original_state = (recipe.name, recipe.size_unit)
        original_servings = list(
            recipe.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        if operation == "create":
            mutation = """
                mutation {
                    createRecipe(
                        name: "Invalid recipe unit", sizeUnit: "unsupported"
                    ) { id }
                }
            """
            variables = None
        else:
            mutation = """
                mutation InvalidUnit($id: ID!) {
                    updateRecipe(
                        id: $id, name: "Changed", sizeUnit: "unsupported"
                    ) { id }
                }
            """
            variables = {"id": str(recipe.id)}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        assert "sizeUnit must be a supported unit" in str(result.errors[0])
        assert Recipe.objects.count() == original_count
        recipe.refresh_from_db()
        assert (recipe.name, recipe.size_unit) == original_state
        assert (
            list(
                recipe.servings.order_by("id").values_list(
                    "id", "serving_size", "serving_unit", "energy_kcal"
                )
            )
            == original_servings
        )

    def test_delete_recipe(self, mocker):
        """Test deleting a recipe."""
        # Given an authenticated user and a recipe
        user = _create_user("rdel@test.com", is_staff=True)
        recipe = Recipe.objects.create(
            name="Bye", size=100, size_unit="g", num_servings=1
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When deleting the recipe
        mutation = "mutation DeleteRecipe($id: ID!) { deleteRecipe(id: $id) }"
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(recipe.id)},
            context_value=mock_context,
        )

        # Then the recipe is deleted
        assert result.errors is None
        assert result.data["deleteRecipe"] is True
        assert not Recipe.objects.filter(pk=recipe.id).exists()

    def test_delete_recipe_rejects_non_staff_user(self, mocker):
        """A regular user cannot delete from the shared recipe catalog."""
        user = _create_user("rdel-regular@test.com")
        recipe = Recipe.objects.create(
            name="Shared Recipe", size=100, size_unit="g", num_servings=1
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = "mutation DeleteRecipe($id: ID!) { deleteRecipe(id: $id) }"

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(recipe.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert Recipe.objects.filter(pk=recipe.id).exists()

    def test_delete_recipe_ingredient_rejects_non_staff_user(self, mocker):
        """A regular user cannot delete a shared recipe ingredient."""
        user = _create_user("ingredient-del-regular@test.com")
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        product = FoodProduct.objects.create(name="Ingredient", num_servings=1)
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe,
            food=product.servings.first(),
            num_servings=1,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation DeleteIngredient($id: ID!) {
                deleteRecipeIngredient(id: $id)
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(ingredient.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert RecipeIngredient.objects.filter(pk=ingredient.id).exists()

    def test_add_recipe_ingredient_rejects_non_staff_user(self, mocker):
        """A regular user cannot add a shared recipe ingredient."""
        user = _create_user("ingredient-add-regular@test.com")
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        product = FoodProduct.objects.create(name="Ingredient", num_servings=1)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation AddIngredient($recipeId: ID!, $foodId: ID!) {
                addRecipeIngredient(
                    recipeId: $recipeId, foodId: $foodId
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "recipeId": str(recipe.id),
                "foodId": str(product.servings.first().id),
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert recipe.ingredients.count() == 0

    def test_staff_can_add_recipe_ingredient(self, mocker):
        """Staff can add a shared recipe ingredient."""
        user = _create_user("ingredient-add-staff@test.com", is_staff=True)
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        product = FoodProduct.objects.create(name="Ingredient", num_servings=1)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation AddIngredient($recipeId: ID!, $foodId: ID!) {
                addRecipeIngredient(
                    recipeId: $recipeId, foodId: $foodId, numServings: 2
                ) { id numServings }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "recipeId": str(recipe.id),
                "foodId": str(product.servings.first().id),
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["addRecipeIngredient"]["numServings"] == 2
        assert recipe.ingredients.count() == 1

    @pytest.mark.parametrize(
        ("operation", "num_servings"), [("add", 0.1), ("update", 99.9)]
    )
    def test_recipe_ingredient_accepts_one_decimal_boundaries(
        self, mocker, operation, num_servings
    ):
        """Ingredient add and update preserve supported one-decimal boundaries."""
        user = _create_user(
            f"ingredient-boundary-{operation}@test.com", is_staff=True
        )
        recipe = Recipe.objects.create(name=f"Boundary {operation}")
        product = FoodProduct.objects.create(name=f"Ingredient {operation}")
        food = product.servings.get(serving_size=100, serving_unit="g")
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe, food=food, num_servings=1
        )
        context = mocker.Mock()
        context.request.user = user
        if operation == "add":
            ingredient.delete()
            mutation = """
                mutation Boundary(
                    $recipeId: ID!, $foodId: ID!, $numServings: Float!
                ) {
                    addRecipeIngredient(
                        recipeId: $recipeId, foodId: $foodId,
                        numServings: $numServings
                    ) { id }
                }
            """
            variables = {
                "recipeId": str(recipe.id),
                "foodId": str(food.id),
                "numServings": num_servings,
            }
        else:
            mutation = """
                mutation Boundary(
                    $id: ID!, $foodId: ID!, $numServings: Float!
                ) {
                    updateRecipeIngredient(
                        id: $id, foodId: $foodId,
                        numServings: $numServings
                    ) { id }
                }
            """
            variables = {
                "id": str(ingredient.id),
                "foodId": str(food.id),
                "numServings": num_servings,
            }

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        persisted = RecipeIngredient.objects.get(
            pk=result.data[
                (
                    "addRecipeIngredient"
                    if operation == "add"
                    else "updateRecipeIngredient"
                )
            ]["id"]
        )
        assert persisted.num_servings == Decimal(str(num_servings))

    @pytest.mark.parametrize(
        "num_servings",
        [0, 0.01, -0.1, float("nan"), float("inf"), -float("inf")],
    )
    def test_add_recipe_ingredient_rejects_invalid_count_without_partial_writes(
        self, mocker, num_servings
    ):
        """An invalid serving count cannot alter ingredient-derived recipe state."""
        user = _create_user("ingredient-zero-staff@test.com", is_staff=True)
        recipe = Recipe.objects.create(
            name="Derived recipe",
            size=10,
            energy_kcal=20,
            nutrients_from_ingredients=True,
        )
        product = FoodProduct.objects.create(
            name="Invalid ingredient",
            size=100,
            energy_kcal=200,
            num_servings=1,
        )
        context = mocker.Mock()
        context.request.user = user
        original_recipe = (recipe.size, recipe.energy_kcal)
        original_servings = list(
            recipe.servings.order_by("id").values_list(
                "id", "serving_size", "energy_kcal"
            )
        )
        mutation = """
            mutation AddIngredient(
                $recipeId: ID!, $foodId: ID!, $numServings: Float!
            ) {
                addRecipeIngredient(
                    recipeId: $recipeId,
                    foodId: $foodId,
                    numServings: $numServings
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "recipeId": str(recipe.id),
                "foodId": str(product.servings.first().id),
                "numServings": num_servings,
            },
            context_value=context,
        )

        assert result.errors is not None
        if num_servings in (0, -0.1):
            assert "numServings must be greater than 0" in str(
                result.errors[0]
            )
        assert recipe.ingredients.count() == 0
        recipe.refresh_from_db()
        assert (recipe.size, recipe.energy_kcal) == original_recipe
        assert (
            list(
                recipe.servings.order_by("id").values_list(
                    "id", "serving_size", "energy_kcal"
                )
            )
            == original_servings
        )

    def test_update_recipe_ingredient_rejects_non_staff_user(self, mocker):
        """A regular user cannot update a shared recipe ingredient."""
        user = _create_user("ingredient-upd-regular@test.com")
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        product = FoodProduct.objects.create(name="Ingredient", num_servings=1)
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe, food=product.servings.first(), num_servings=1
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateIngredient($id: ID!, $foodId: ID!) {
                updateRecipeIngredient(
                    id: $id, foodId: $foodId, numServings: 2
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(ingredient.id),
                "foodId": str(product.servings.first().id),
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        ingredient.refresh_from_db()
        assert ingredient.num_servings == 1

    def test_staff_can_update_recipe_ingredient(self, mocker):
        """Staff can update a shared recipe ingredient."""
        user = _create_user("ingredient-upd-staff@test.com", is_staff=True)
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        product = FoodProduct.objects.create(name="Ingredient", num_servings=1)
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe, food=product.servings.first(), num_servings=1
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateIngredient($id: ID!, $foodId: ID!) {
                updateRecipeIngredient(
                    id: $id, foodId: $foodId, numServings: 2
                ) { numServings }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(ingredient.id),
                "foodId": str(product.servings.first().id),
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateRecipeIngredient"]["numServings"] == 2
        ingredient.refresh_from_db()
        assert ingredient.num_servings == 2

    @pytest.mark.parametrize(
        "num_servings",
        [0, 0.01, -0.1, float("nan"), float("inf"), -float("inf")],
    )
    def test_update_recipe_ingredient_rejects_invalid_count_without_partial_writes(
        self, mocker, num_servings
    ):
        """An invalid update leaves ingredient and derived recipe state unchanged."""
        user = _create_user("ingredient-update-zero@test.com", is_staff=True)
        recipe = Recipe.objects.create(
            name="Derived update recipe", nutrients_from_ingredients=True
        )
        original_product = FoodProduct.objects.create(
            name="Original ingredient",
            size=100,
            energy_kcal=200,
            num_servings=1,
        )
        replacement_product = FoodProduct.objects.create(
            name="Replacement ingredient",
            size=50,
            energy_kcal=50,
            num_servings=1,
        )
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe,
            food=original_product.servings.first(),
            num_servings=1,
        )
        recipe.refresh_from_db()
        context = mocker.Mock()
        context.request.user = user
        original_ingredient = (
            ingredient.food_id,
            ingredient.num_servings,
            ingredient.energy_kcal,
        )
        original_recipe = (recipe.size, recipe.energy_kcal)
        original_servings = list(
            recipe.servings.order_by("id").values_list(
                "id", "serving_size", "energy_kcal"
            )
        )
        mutation = """
            mutation UpdateIngredient(
                $id: ID!, $foodId: ID!, $numServings: Float!
            ) {
                updateRecipeIngredient(
                    id: $id,
                    foodId: $foodId,
                    numServings: $numServings
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(ingredient.id),
                "foodId": str(replacement_product.servings.first().id),
                "numServings": num_servings,
            },
            context_value=context,
        )

        assert result.errors is not None
        if num_servings in (0, -0.1):
            assert "numServings must be greater than 0" in str(
                result.errors[0]
            )
        ingredient.refresh_from_db()
        assert (
            ingredient.food_id,
            ingredient.num_servings,
            ingredient.energy_kcal,
        ) == original_ingredient
        recipe.refresh_from_db()
        assert (recipe.size, recipe.energy_kcal) == original_recipe
        assert (
            list(
                recipe.servings.order_by("id").values_list(
                    "id", "serving_size", "energy_kcal"
                )
            )
            == original_servings
        )

    @pytest.mark.parametrize("operation", ["add", "update"])
    def test_recipe_ingredient_rejects_derived_nutrient_overflow_atomically(
        self, mocker, operation
    ):
        """Snapshot multiplication is validated before any aggregate write."""
        user = _create_user(
            f"ingredient-derived-overflow-{operation}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Derived overflow parent",
            nutrients_from_ingredients=True,
            size=0,
        )
        product = FoodProduct.objects.create(
            name="Derived overflow ingredient",
            nutritional_info_size=1,
            size=1,
            energy_kcal=1,
        )
        serving = product.servings.get(
            serving_size=1, serving_unit="container"
        )
        ingredient = None
        if operation == "update":
            ingredient = RecipeIngredient.objects.create(
                recipe=recipe, food=serving, num_servings=1
            )
        recipe.refresh_from_db()
        original_recipe = (recipe.size, recipe.energy_kcal)
        original_ingredients = list(
            recipe.ingredients.values_list(
                "pk", "num_servings", "size_snapshot", "energy_kcal"
            )
        )
        mutation_name = (
            "addRecipeIngredient"
            if operation == "add"
            else "updateRecipeIngredient"
        )
        if operation == "add":
            identifier = f'recipeId: "{recipe.pk}"'
        else:
            assert ingredient is not None
            identifier = f'id: "{ingredient.pk}"'

        result = schema.execute_sync(
            f"""
            mutation {{
                {mutation_name}(
                    {identifier}, foodId: "{serving.pk}",
                    numServings: 100000000
                ) {{ id }}
            }}
            """,
            context_value=context,
        )

        assert result.errors is not None
        assert (
            "Recipe ingredient energyKcal exceeds supported precision"
            in str(result.errors[0])
        )
        recipe.refresh_from_db()
        assert (recipe.size, recipe.energy_kcal) == original_recipe
        assert (
            list(
                recipe.ingredients.values_list(
                    "pk", "num_servings", "size_snapshot", "energy_kcal"
                )
            )
            == original_ingredients
        )

    def test_recipe_ingredient_rejects_derived_size_overflow_atomically(
        self, mocker
    ):
        """Ingredient size multiplication is checked against its snapshot field."""
        user = _create_user(
            "recipe-size-snapshot-overflow@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Size snapshot overflow parent",
            nutrients_from_ingredients=True,
            size=0,
        )
        product = FoodProduct.objects.create(
            name="Size snapshot overflow ingredient",
            size=Decimal("100000000"),
        )
        serving = product.servings.get(
            serving_size=1, serving_unit="container"
        )

        result = schema.execute_sync(
            f"""
            mutation {{
                addRecipeIngredient(
                    recipeId: "{recipe.pk}", foodId: "{serving.pk}",
                    numServings: 100
                ) {{ id }}
            }}
            """,
            context_value=context,
        )

        assert result.errors is not None
        assert (
            "Recipe ingredient sizeSnapshot exceeds supported precision"
            in str(result.errors[0])
        )
        assert recipe.ingredients.count() == 0
        recipe.refresh_from_db()
        assert recipe.size == Decimal("0.0")

    def test_recipe_ingredient_rejects_recipe_size_overflow_atomically(
        self, mocker
    ):
        """A valid historical snapshot must also fit the Recipe size field."""
        user = _create_user(
            "recipe-total-size-overflow@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Recipe size overflow parent",
            nutrients_from_ingredients=True,
            size=0,
        )
        product = FoodProduct.objects.create(
            name="Recipe size overflow ingredient",
            size=Decimal("600000000"),
        )
        serving = product.servings.get(
            serving_size=1, serving_unit="container"
        )

        result = schema.execute_sync(
            f"""
            mutation {{
                addRecipeIngredient(
                    recipeId: "{recipe.pk}", foodId: "{serving.pk}",
                    numServings: 2
                ) {{ id }}
            }}
            """,
            context_value=context,
        )

        assert result.errors is not None
        assert "Recipe size exceeds supported precision" in str(
            result.errors[0]
        )
        assert recipe.ingredients.count() == 0
        recipe.refresh_from_db()
        assert recipe.size == Decimal("0.0")

    def test_recipe_ingredient_rejects_aggregate_sum_overflow_atomically(
        self, mocker
    ):
        """An aggregate sum outside Recipe fields rejects the whole mutation."""
        user = _create_user(
            "recipe-aggregate-overflow@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Aggregate overflow parent",
            nutrients_from_ingredients=True,
            size=0,
        )
        product = FoodProduct.objects.create(
            name="Aggregate overflow ingredient",
            nutritional_info_size=1,
            size=1,
            energy_kcal=Decimal("60000000"),
        )
        serving = product.servings.get(
            serving_size=1, serving_unit="container"
        )
        RecipeIngredient.objects.create(recipe=recipe, food=serving)
        recipe.refresh_from_db()
        original_recipe = (recipe.size, recipe.energy_kcal)
        original_ingredients = list(
            recipe.ingredients.values_list("pk", "energy_kcal")
        )

        result = schema.execute_sync(
            f"""
            mutation {{
                addRecipeIngredient(
                    recipeId: "{recipe.pk}", foodId: "{serving.pk}"
                ) {{ id }}
            }}
            """,
            context_value=context,
        )

        assert result.errors is not None
        assert "Recipe energyKcal exceeds supported precision" in str(
            result.errors[0]
        )
        recipe.refresh_from_db()
        assert (recipe.size, recipe.energy_kcal) == original_recipe
        assert (
            list(recipe.ingredients.values_list("pk", "energy_kcal"))
            == original_ingredients
        )

    @pytest.mark.parametrize("operation", ["add", "update"])
    def test_recipe_ingredient_rejects_decimal_overflow_before_side_effects(
        self, mocker, operation
    ):
        """Ingredient quantity precision is checked before parent signals run."""
        user = _create_user(
            f"ingredient-overflow-{operation}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Overflow parent",
            nutrients_from_ingredients=True,
            size=10,
            energy_kcal=20,
        )
        product = FoodProduct.objects.create(
            name="Overflow serving", size=100, energy_kcal=100
        )
        ingredient = None
        if operation == "update":
            ingredient = RecipeIngredient.objects.create(
                recipe=recipe, food=product.servings.first(), num_servings=1
            )
        recipe.refresh_from_db()
        original_recipe = (recipe.size, recipe.energy_kcal)
        original_count = recipe.ingredients.count()
        mutation_name = (
            "addRecipeIngredient"
            if operation == "add"
            else "updateRecipeIngredient"
        )
        identifier = (
            f'recipeId: "{recipe.pk}"'
            if operation == "add"
            else f'id: "{ingredient.pk}"'
        )
        mutation = f"""
            mutation {{
                {mutation_name}(
                    {identifier}, foodId: "{product.servings.first().pk}",
                    numServings: 1000000000
                ) {{ id }}
            }}
        """

        result = schema.execute_sync(mutation, context_value=context)

        assert result.errors is not None
        assert "numServings exceeds supported precision" in str(
            result.errors[0]
        )
        recipe.refresh_from_db()
        assert (recipe.size, recipe.energy_kcal) == original_recipe
        assert recipe.ingredients.count() == original_count

    @pytest.mark.parametrize("operation", ["add", "update"])
    # pylint: disable-next=R0914
    def test_recipe_ingredient_mutation_rolls_back_signal_side_effects(
        self, mocker, operation
    ):
        """A late ingredient failure rolls back ingredient and parent updates."""
        user = _create_user(
            f"ingredient-atomic-{operation}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        recipe = Recipe.objects.create(
            name="Atomic parent", nutrients_from_ingredients=True
        )
        product = FoodProduct.objects.create(
            name="Atomic serving", energy_kcal=100
        )
        ingredient = None
        if operation == "update":
            ingredient = RecipeIngredient.objects.create(
                recipe=recipe, food=product.servings.first(), num_servings=1
            )
        recipe.refresh_from_db()
        original_recipe = (recipe.size, recipe.energy_kcal)
        original_ingredients = list(
            recipe.ingredients.values_list(
                "pk", "food_id", "num_servings", "energy_kcal"
            )
        )
        real_save = RecipeIngredient.save

        def save_then_fail(instance, *args, **kwargs):
            real_save(instance, *args, **kwargs)
            raise RuntimeError("injected late persistence failure")

        mocker.patch.object(RecipeIngredient, "save", save_then_fail)
        mutation_name = (
            "addRecipeIngredient"
            if operation == "add"
            else "updateRecipeIngredient"
        )
        identifier = (
            f'recipeId: "{recipe.pk}"'
            if operation == "add"
            else f'id: "{ingredient.pk}"'
        )
        mutation = f"""
            mutation {{
                {mutation_name}(
                    {identifier}, foodId: "{product.servings.first().pk}",
                    numServings: 2
                ) {{ id }}
            }}
        """

        result = schema.execute_sync(mutation, context_value=context)

        assert result.errors is not None
        recipe.refresh_from_db()
        assert (recipe.size, recipe.energy_kcal) == original_recipe
        assert (
            list(
                recipe.ingredients.values_list(
                    "pk", "food_id", "num_servings", "energy_kcal"
                )
            )
            == original_ingredients
        )

    def test_staff_can_delete_recipe_ingredient(self, mocker):
        """Staff can delete a shared recipe ingredient."""
        user = _create_user("ingredient-del-staff@test.com", is_staff=True)
        recipe = Recipe.objects.create(name="Shared", num_servings=1)
        product = FoodProduct.objects.create(name="Ingredient", num_servings=1)
        ingredient = RecipeIngredient.objects.create(
            recipe=recipe,
            food=product.servings.first(),
            num_servings=1,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation DeleteIngredient($id: ID!) {
                deleteRecipeIngredient(id: $id)
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(ingredient.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["deleteRecipeIngredient"] is True
        assert not RecipeIngredient.objects.filter(pk=ingredient.id).exists()

    def test_create_recipe_unauthenticated(self):
        """Test creating a recipe without authentication."""
        # When attempting to create a recipe without authentication
        mutation = """
            mutation CreateRecipe($name: String!) {
                createRecipe(name: $name) { id }
            }
        """
        result = schema.execute_sync(
            mutation, variable_values={"name": "Fail"}, context_value=None
        )

        # Then the result contains an error
        assert result.errors is not None
