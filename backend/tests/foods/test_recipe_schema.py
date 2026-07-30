"""Tests for Recipes GraphQL schema."""

import pytest
from django.contrib.auth import get_user_model

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


@pytest.mark.django_db
class TestRecipeMutation:
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
        "size", [0.0, -1.0, float("nan"), float("inf"), -float("inf")]
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

    @pytest.mark.parametrize("num_servings", [0.0, -1.0])
    def test_create_recipe_rejects_non_positive_serving_count(
        self, mocker, num_servings
    ):
        """Creating a recipe requires a positive serving count."""
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
        assert "numServings must be greater than 0" in str(result.errors[0])
        assert not Recipe.objects.filter(name="Invalid").exists()

    @pytest.mark.parametrize(
        "size", [0.0, -1.0, float("nan"), float("inf"), -float("inf")]
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

    @pytest.mark.parametrize("num_servings", [0.0, -1.0])
    def test_update_recipe_rejects_non_positive_serving_count(
        self, mocker, num_servings
    ):
        """Updating a recipe requires a positive serving count."""
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
        assert "numServings must be greater than 0" in str(result.errors[0])
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
    @pytest.mark.parametrize("value", [-0.1, float("nan"), float("inf")])
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
