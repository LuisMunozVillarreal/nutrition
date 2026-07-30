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
        user = _create_user("rc@test.com")

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

    def test_update_recipe(self, mocker):
        """Test updating a recipe."""
        # Given an authenticated user and a recipe
        user = _create_user("ru@test.com")
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

    @pytest.mark.parametrize("num_servings", [0.0, -1.0])
    def test_create_recipe_rejects_non_positive_serving_count(
        self, mocker, num_servings
    ):
        """Creating a recipe requires a positive serving count."""
        user = _create_user(f"rc-invalid-{num_servings}@test.com")
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

    @pytest.mark.parametrize("num_servings", [0.0, -1.0])
    def test_update_recipe_rejects_non_positive_serving_count(
        self, mocker, num_servings
    ):
        """Updating a recipe requires a positive serving count."""
        user = _create_user(f"ru-invalid-{num_servings}@test.com")
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
