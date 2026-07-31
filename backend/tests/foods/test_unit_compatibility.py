"""Dimensional compatibility tests for product and serving mutations."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

from apps.foods.models import FoodProduct
from config.schema import schema

User = get_user_model()


def _staff_context(mocker, email):
    """Return a GraphQL context for a staff catalog editor."""
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


def _product_mutation(operation):
    """Return a complete product mutation for create or update."""
    if operation == "create":
        return """
            mutation ProductUnits(
                $name: String!, $sizeUnit: String!,
                $nutritionalInfoUnit: String!
            ) {
                createFoodProduct(
                    name: $name, size: 500, sizeUnit: $sizeUnit,
                    nutritionalInfoSize: 100,
                    nutritionalInfoUnit: $nutritionalInfoUnit,
                    numServings: 5, energyKcal: 200, proteinG: 20
                ) { id }
            }
        """
    return """
        mutation ProductUnits(
            $id: ID!, $name: String!, $sizeUnit: String!,
            $nutritionalInfoUnit: String!
        ) {
            updateFoodProduct(
                id: $id, name: $name, size: 500, sizeUnit: $sizeUnit,
                nutritionalInfoSize: 100,
                nutritionalInfoUnit: $nutritionalInfoUnit,
                numServings: 5, energyKcal: 200, proteinG: 20
            ) { id }
        }
    """


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    ("size_unit", "nutritional_info_unit"),
    [
        ("g", "ml"),
        ("l", "kg"),
        ("unit", "g"),
        ("ml", "container"),
        ("unit", "serving"),
        ("container", "serving"),
    ],
)
def test_product_rejects_dimensionally_incompatible_units_before_signals(
    mocker, operation, size_unit, nutritional_info_unit
):
    """Invalid product unit pairs cause no persistence or post-save effects."""
    context = _staff_context(
        mocker,
        f"product-units-{operation}-{size_unit}-{nutritional_info_unit}@test.com",
    )
    product = FoodProduct.objects.create(
        name="Original dimensional product",
        size=500,
        size_unit="g",
        nutritional_info_size=100,
        nutritional_info_unit="g",
        num_servings=5,
        energy_kcal=200,
        protein_g=20,
    )
    original_count = FoodProduct.objects.count()
    original_state = tuple(
        getattr(product, field)
        for field in (
            "name",
            "size",
            "size_unit",
            "nutritional_info_size",
            "nutritional_info_unit",
            "energy_kcal",
            "protein_g",
        )
    )
    original_servings = list(
        product.servings.order_by("id").values_list(
            "id", "serving_size", "serving_unit", "energy_kcal", "protein_g"
        )
    )
    observed_saves = []

    def observe_save(
        sender, instance, **kwargs
    ):  # pylint: disable=unused-argument
        observed_saves.append(instance.pk)

    post_save.connect(
        observe_save,
        sender=FoodProduct,
        dispatch_uid="test-product-dimensional-validation",
    )
    try:
        variables = {
            "name": "Dimensionally invalid product",
            "sizeUnit": size_unit,
            "nutritionalInfoUnit": nutritional_info_unit,
        }
        if operation == "update":
            variables["id"] = str(product.id)
        result = schema.execute_sync(
            _product_mutation(operation),
            variable_values=variables,
            context_value=context,
        )
    finally:
        post_save.disconnect(
            sender=FoodProduct,
            dispatch_uid="test-product-dimensional-validation",
        )

    assert result.errors is not None
    assert "sizeUnit must be compatible with nutritionalInfoUnit" in str(
        result.errors[0]
    )
    assert not observed_saves
    assert FoodProduct.objects.count() == original_count
    product.refresh_from_db()
    assert (
        tuple(
            getattr(product, field)
            for field in (
                "name",
                "size",
                "size_unit",
                "nutritional_info_size",
                "nutritional_info_unit",
                "energy_kcal",
                "protein_g",
            )
        )
        == original_state
    )
    assert (
        list(
            product.servings.order_by("id").values_list(
                "id",
                "serving_size",
                "serving_unit",
                "energy_kcal",
                "protein_g",
            )
        )
        == original_servings
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("size", "size_unit", "info_size", "info_unit", "expected_energy"),
    [
        (1, "kg", 100, "g", Decimal("1000")),
        (1, "l", 100, "ml", Decimal("1000")),
        (1, "floz", 100, "ml", Decimal("29.57")),
        (1, "c", 100, "ml", Decimal("236.59")),
        (8, "unit", 1, "unit", Decimal("800")),
        (2, "container", 1, "container", Decimal("200")),
        (2, "serving", 1, "serving", Decimal("200")),
    ],
)
def test_product_accepts_convertible_and_same_contextual_units(
    mocker, size, size_unit, info_size, info_unit, expected_energy
):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Concrete same-dimension and exact contextual pairs remain meaningful."""
    context = _staff_context(
        mocker, f"valid-product-units-{size_unit}-{info_unit}@test.com"
    )
    mutation = """
        mutation ValidProductUnits(
            $size: Float!, $sizeUnit: String!, $infoSize: Float!,
            $infoUnit: String!
        ) {
            createFoodProduct(
                name: "Valid dimensional product",
                size: $size, sizeUnit: $sizeUnit,
                nutritionalInfoSize: $infoSize,
                nutritionalInfoUnit: $infoUnit,
                numServings: 1, energyKcal: 100
            ) { id }
        }
    """

    result = schema.execute_sync(
        mutation,
        variable_values={
            "size": float(size),
            "sizeUnit": size_unit,
            "infoSize": float(info_size),
            "infoUnit": info_unit,
        },
        context_value=context,
    )

    assert result.errors is None
    product = FoodProduct.objects.get(
        pk=result.data["createFoodProduct"]["id"]
    )
    container_energies = list(
        product.servings.filter(serving_unit="container").values_list(
            "energy_kcal", flat=True
        )
    )
    assert container_energies
    assert all(energy == expected_energy for energy in container_energies)


@pytest.mark.django_db
def test_product_update_accepts_compatible_unit_conversions(mocker):
    """Updating within a dimension recalculates every existing serving."""
    context = _staff_context(mocker, "valid-product-update-units@test.com")
    product = FoodProduct.objects.create(
        name="Grams product",
        size=500,
        size_unit="g",
        nutritional_info_size=100,
        nutritional_info_unit="g",
        num_servings=5,
        energy_kcal=100,
    )

    result = schema.execute_sync(
        _product_mutation("update"),
        variable_values={
            "id": str(product.id),
            "name": "Kilograms product",
            "sizeUnit": "kg",
            "nutritionalInfoUnit": "g",
        },
        context_value=context,
    )

    assert result.errors is None
    product.refresh_from_db()
    assert product.size_unit == "kg"
    assert (
        product.servings.get(serving_unit="container").energy_kcal == 1000000
    )


@pytest.mark.django_db
def test_product_update_rejects_units_incompatible_with_existing_servings(
    mocker,
):
    """A valid new product pair cannot strand existing concrete servings."""
    context = _staff_context(mocker, "product-existing-serving-units@test.com")
    product = FoodProduct.objects.create(
        name="Mass product",
        size=500,
        size_unit="g",
        nutritional_info_size=100,
        nutritional_info_unit="g",
        num_servings=5,
    )
    original_state = (
        product.name,
        product.size_unit,
        product.nutritional_info_unit,
    )
    original_servings = list(
        product.servings.order_by("id").values_list(
            "id", "serving_size", "serving_unit", "energy_kcal"
        )
    )

    result = schema.execute_sync(
        _product_mutation("update"),
        variable_values={
            "id": str(product.id),
            "name": "Volume product",
            "sizeUnit": "l",
            "nutritionalInfoUnit": "ml",
        },
        context_value=context,
    )

    assert result.errors is not None
    assert "Existing servingUnit must be compatible with product units" in str(
        result.errors[0]
    )
    product.refresh_from_db()
    assert (
        product.name,
        product.size_unit,
        product.nutritional_info_unit,
    ) == (original_state)
    assert (
        list(
            product.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        == original_servings
    )


def _serving_mutation(operation):
    """Return a serving mutation for create or update."""
    if operation == "create":
        return """
            mutation ServingUnits($foodId: ID!, $servingUnit: String!) {
                createServing(
                    foodId: $foodId, servingSize: 1,
                    servingUnit: $servingUnit
                ) { id }
            }
        """
    return """
        mutation ServingUnits($id: ID!, $servingUnit: String!) {
            updateServing(
                id: $id, servingSize: 1, servingUnit: $servingUnit
            ) { id }
        }
    """


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    ("size_unit", "info_unit", "serving_unit"),
    [
        ("g", "g", "ml"),
        ("g", "g", "unit"),
        ("unit", "unit", "g"),
        ("ml", "g", "g"),
    ],
)
def test_serving_rejects_units_incompatible_with_product_without_partial_writes(
    mocker, operation, size_unit, info_unit, serving_unit
):
    """Serving validation covers package and nutrition dimensions on all paths."""
    context = _staff_context(
        mocker,
        f"serving-units-{operation}-{size_unit}-{info_unit}-{serving_unit}@test.com",
    )
    product = FoodProduct.objects.create(
        name="Serving compatibility product",
        size=500,
        size_unit="g",
        nutritional_info_size=100,
        nutritional_info_unit="g",
        num_servings=5,
        energy_kcal=100,
    )
    if size_unit != "g" or info_unit != "g":
        FoodProduct.objects.filter(pk=product.pk).update(
            size_unit=size_unit, nutritional_info_unit=info_unit
        )
        product.refresh_from_db()
    serving = product.servings.get(serving_size=100, serving_unit="g")
    original_ids = set(product.servings.values_list("id", flat=True))
    original_state = (
        serving.serving_size,
        serving.serving_unit,
        serving.energy_kcal,
    )
    variables = {"servingUnit": serving_unit}
    if operation == "create":
        variables["foodId"] = str(product.id)
    else:
        variables["id"] = str(serving.id)

    result = schema.execute_sync(
        _serving_mutation(operation),
        variable_values=variables,
        context_value=context,
    )

    assert result.errors is not None
    assert "servingUnit must be compatible with product units" in str(
        result.errors[0]
    )
    assert set(product.servings.values_list("id", flat=True)) == original_ids
    serving.refresh_from_db()
    assert (
        serving.serving_size,
        serving.serving_unit,
        serving.energy_kcal,
    ) == original_state


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    ("size_unit", "info_unit", "serving_unit"),
    [
        ("g", "g", "oz"),
        ("l", "ml", "floz"),
        ("g", "g", "container"),
        ("g", "g", "serving"),
        ("unit", "unit", "unit"),
        ("unit", "unit", "container"),
        ("unit", "unit", "serving"),
    ],
)
def test_serving_accepts_convertible_and_resolvable_contextual_units(
    mocker, operation, size_unit, info_unit, serving_unit
):
    """Serving units support conversion and valid container semantics."""
    context = _staff_context(
        mocker,
        f"valid-serving-units-{size_unit}-{info_unit}-{serving_unit}@test.com",
    )
    product = FoodProduct.objects.create(
        name="Valid serving compatibility product",
        size=8 if size_unit == "unit" else 500,
        size_unit=size_unit,
        nutritional_info_size=1 if info_unit == "unit" else 100,
        nutritional_info_unit=info_unit,
        num_servings=4,
        energy_kcal=100,
    )

    result = schema.execute_sync(
        _serving_mutation("create"),
        variable_values={
            "foodId": str(product.id),
            "servingUnit": serving_unit,
        },
        context_value=context,
    )

    assert result.errors is None
    created = product.servings.get(pk=result.data["createServing"]["id"])
    assert created.energy_kcal > 0
