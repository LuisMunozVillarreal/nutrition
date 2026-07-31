"""Recipe GraphQL unit-consistency regression tests."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.foods.models import FoodProduct, Recipe, RecipeIngredient, Serving
from config.schema import schema

User = get_user_model()

ADVERTISED_RECIPE_SIZE_UNITS = (
    "g",
    "ml",
    "floz",
    "oz",
    "container",
    "serving",
)


def _staff_context(mocker, email):
    """Create a GraphQL context for an authenticated staff user."""
    user = User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
        is_staff=True,
    )
    context = mocker.Mock()
    context.request.user = user
    return context


@pytest.mark.django_db
@pytest.mark.parametrize("size_unit", ADVERTISED_RECIPE_SIZE_UNITS)
def test_create_recipe_supports_every_advertised_size_unit(mocker, size_unit):
    """Recipe nutrients are totals independent of the selected size unit."""
    context = _staff_context(mocker, f"recipe-create-{size_unit}@test.com")
    mutation = """
        mutation CreateRecipe($sizeUnit: String!) {
            createRecipe(
                name: "Unit-consistent recipe",
                size: 200,
                sizeUnit: $sizeUnit,
                numServings: 4,
                energyKcal: 400,
                proteinG: 40
            ) { id }
        }
    """

    result = schema.execute_sync(
        mutation,
        variable_values={"sizeUnit": size_unit},
        context_value=context,
    )

    assert result.errors is None
    recipe = Recipe.objects.get(name="Unit-consistent recipe")
    assert recipe.size_unit == size_unit
    assert recipe.nutritional_info_unit == size_unit
    serving = recipe.servings.get()
    assert serving.serving_size == 1
    assert serving.serving_unit == "serving"
    assert serving.energy_kcal == 100
    assert serving.protein_g == 10


@pytest.mark.django_db
@pytest.mark.parametrize("size_unit", ADVERTISED_RECIPE_SIZE_UNITS)
def test_update_recipe_supports_every_advertised_size_unit(mocker, size_unit):
    """Recipe updates preserve total nutrients and serving proportions."""
    context = _staff_context(mocker, f"recipe-update-{size_unit}@test.com")
    recipe = Recipe.objects.create(
        name="Original unit recipe",
        size=100,
        size_unit="g",
        nutritional_info_unit="g",
        num_servings=2,
        energy_kcal=200,
        protein_g=20,
    )
    mutation = """
        mutation UpdateRecipe($id: ID!, $sizeUnit: String!) {
            updateRecipe(
                id: $id,
                name: "Updated unit recipe",
                size: 200,
                sizeUnit: $sizeUnit,
                numServings: 4,
                energyKcal: 400,
                proteinG: 40
            ) { id }
        }
    """

    result = schema.execute_sync(
        mutation,
        variable_values={"id": str(recipe.pk), "sizeUnit": size_unit},
        context_value=context,
    )

    assert result.errors is None
    recipe.refresh_from_db()
    assert recipe.name == "Updated unit recipe"
    assert recipe.size_unit == size_unit
    assert recipe.nutritional_info_unit == size_unit
    assert recipe.servings.count() == 1
    serving = recipe.servings.get()
    assert serving.energy_kcal == 100
    assert serving.protein_g == 10


@pytest.mark.django_db
def test_same_unit_graphql_update_preserves_ingredient_derived_aggregates(
    mocker,
):
    """Client totals cannot overwrite authoritative ingredient-derived values."""
    context = _staff_context(mocker, "recipe-derived-update@test.com")
    recipe = Recipe.objects.create(
        name="Derived recipe",
        size=0,
        size_unit="g",
        nutritional_info_unit="g",
        num_servings=2,
        nutrients_from_ingredients=True,
    )
    product = FoodProduct.objects.create(
        name="Derived ingredient",
        size=Decimal("100"),
        size_unit="g",
        nutritional_info_unit="g",
        energy_kcal=Decimal("240"),
        protein_g=Decimal("12"),
    )
    RecipeIngredient.objects.create(
        recipe=recipe,
        food=product.servings.get(serving_size=100, serving_unit="g"),
        num_servings=Decimal("2"),
    )
    recipe.refresh_from_db()
    assert (recipe.size, recipe.energy_kcal, recipe.protein_g) == (
        Decimal("200.0"),
        Decimal("480.00"),
        Decimal("24.00"),
    )

    result = schema.execute_sync(
        """
        mutation UpdateDerived($id: ID!) {
            updateRecipe(
                id: $id,
                name: "Renamed derived recipe",
                size: 1,
                sizeUnit: "g",
                numServings: 4,
                energyKcal: 1,
                proteinG: 1
            ) { id size energyKcal proteinG numServings }
        }
        """,
        variable_values={"id": str(recipe.pk)},
        context_value=context,
    )

    assert result.errors is None
    recipe.refresh_from_db()
    assert recipe.name == "Renamed derived recipe"
    assert recipe.num_servings == Decimal("4.0")
    assert (recipe.size, recipe.energy_kcal, recipe.protein_g) == (
        Decimal("200.0"),
        Decimal("480.00"),
        Decimal("24.00"),
    )
    serving = recipe.servings.get()
    assert (serving.energy_kcal, serving.protein_g) == (
        Decimal("120.00"),
        Decimal("6.00"),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["create", "update"])
def test_invalid_recipe_unit_rolls_back_recipe_and_serving_writes(
    mocker, operation
):
    """Invalid recipe units cannot partially persist a recipe or serving."""
    context = _staff_context(mocker, f"recipe-invalid-{operation}@test.com")
    recipe = Recipe.objects.create(
        name="Original recipe",
        size=100,
        size_unit="g",
        nutritional_info_unit="g",
        num_servings=2,
        energy_kcal=200,
    )
    original_recipe_count = Recipe.objects.count()
    original_serving_count = Serving.objects.count()
    original_state = (
        recipe.name,
        recipe.size,
        recipe.size_unit,
        recipe.nutritional_info_unit,
        recipe.num_servings,
        recipe.energy_kcal,
    )
    original_servings = list(
        recipe.servings.order_by("id").values_list(
            "id", "serving_size", "serving_unit", "energy_kcal"
        )
    )
    if operation == "create":
        mutation = """
            mutation {
                createRecipe(
                    name: "Invalid recipe", sizeUnit: "unsupported"
                ) { id }
            }
        """
        variables = None
    else:
        mutation = """
            mutation InvalidRecipeUnit($id: ID!) {
                updateRecipe(
                    id: $id,
                    name: "Changed recipe",
                    size: 200,
                    sizeUnit: "unsupported",
                    numServings: 4,
                    energyKcal: 400
                ) { id }
            }
        """
        variables = {"id": str(recipe.pk)}

    result = schema.execute_sync(
        mutation, variable_values=variables, context_value=context
    )

    assert result.errors is not None
    assert "sizeUnit must be a supported unit" in str(result.errors[0])
    assert Recipe.objects.count() == original_recipe_count
    assert Serving.objects.count() == original_serving_count
    recipe.refresh_from_db()
    assert (
        recipe.name,
        recipe.size,
        recipe.size_unit,
        recipe.nutritional_info_unit,
        recipe.num_servings,
        recipe.energy_kcal,
    ) == original_state
    assert (
        list(
            recipe.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        == original_servings
    )


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["create", "update"])
def test_recipe_mutation_rolls_back_late_serving_failure(mocker, operation):
    """A generated-serving failure rolls back recipe and serving writes."""
    context = _staff_context(mocker, f"recipe-late-{operation}@test.com")
    recipe = Recipe.objects.create(
        name="Atomic original",
        size=100,
        size_unit="g",
        nutritional_info_unit="g",
        num_servings=2,
        energy_kcal=200,
    )
    original_recipe_count = Recipe.objects.count()
    original_serving_count = Serving.objects.count()
    original_state = (
        recipe.name,
        recipe.size,
        recipe.size_unit,
        recipe.nutritional_info_unit,
        recipe.num_servings,
        recipe.energy_kcal,
    )
    original_servings = list(
        recipe.servings.order_by("id").values_list(
            "id", "serving_size", "serving_unit", "energy_kcal"
        )
    )
    real_save = Serving.save

    def save_then_fail(instance, *args, **kwargs):
        real_save(instance, *args, **kwargs)
        raise RuntimeError("injected late serving failure")

    mocker.patch.object(Serving, "save", save_then_fail)
    if operation == "create":
        mutation = """
            mutation {
                createRecipe(
                    name: "Atomic new",
                    size: 200,
                    sizeUnit: "ml",
                    numServings: 4,
                    energyKcal: 400
                ) { id }
            }
        """
        variables = None
    else:
        mutation = """
            mutation AtomicRecipeUpdate($id: ID!) {
                updateRecipe(
                    id: $id,
                    name: "Atomic changed",
                    size: 200,
                    sizeUnit: "ml",
                    numServings: 4,
                    energyKcal: 400
                ) { id }
            }
        """
        variables = {"id": str(recipe.pk)}

    result = schema.execute_sync(
        mutation, variable_values=variables, context_value=context
    )

    assert result.errors is not None
    assert "injected late serving failure" in str(result.errors[0])
    assert Recipe.objects.count() == original_recipe_count
    assert Serving.objects.count() == original_serving_count
    recipe.refresh_from_db()
    assert (
        recipe.name,
        recipe.size,
        recipe.size_unit,
        recipe.nutritional_info_unit,
        recipe.num_servings,
        recipe.energy_kcal,
    ) == original_state
    assert (
        list(
            recipe.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        == original_servings
    )
