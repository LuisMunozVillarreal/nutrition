"""Tests for FoodProducts and Servings GraphQL schema."""

# The product and serving mutation matrices intentionally exercise every
# exposed field in both create and update paths.
# pylint: disable=too-many-lines

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.foods.models import FoodProduct, Serving
from apps.foods.schema import (
    _validated_product_num_servings,
    _validated_product_nutritional_info_size,
)
from apps.libs.graphql import validated_positive_decimal
from config.schema import schema

User = get_user_model()


@pytest.mark.parametrize(
    "num_servings", [float("nan"), float("inf"), -float("inf")]
)
def test_product_num_servings_must_be_finite(num_servings):
    """Non-finite product serving counts are rejected."""
    with pytest.raises(ValueError, match="numServings must be greater than 0"):
        _validated_product_num_servings(num_servings)


@pytest.mark.parametrize(
    "nutritional_info_size",
    [0.0, -1.0, float("nan"), float("inf"), -float("inf")],
)
def test_product_nutritional_info_size_must_be_finite_and_positive(
    nutritional_info_size,
):
    """Every invalid nutrition basis is rejected by product validation."""
    with pytest.raises(
        ValueError, match="nutritionalInfoSize must be greater than 0"
    ):
        _validated_product_nutritional_info_size(nutritional_info_size)


@pytest.mark.parametrize(
    "value", [0.0, -1.0, float("nan"), float("inf"), -float("inf")]
)
def test_positive_decimal_validation_rejects_every_invalid_float(value):
    """Shared server validation rejects non-positive and non-finite inputs."""
    with pytest.raises(ValueError, match="fieldName must be greater than 0"):
        validated_positive_decimal(value, "fieldName")


def _create_user(email: str, *, is_staff: bool = False):
    """Create a user."""
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
        is_staff=is_staff,
    )


@pytest.mark.django_db
class TestFoodProductSchema:
    """Tests for FoodProduct mutations and queries."""

    def _count_food_products_with_servings_query(
        self, mocker, product_count: int
    ) -> int:
        """Create products and count SQL queries for nested servings query."""
        user = _create_user(f"fp-query-{product_count}-count@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        for index in range(product_count):
            FoodProduct.objects.create(
                name=f"Product {index}",
                size=100,
                size_unit="g",
                num_servings=1,
                nutritional_info_size=100,
                nutritional_info_unit="g",
            )

        query = "{ foodProducts { id name servings { id energyKcal } } }"
        with CaptureQueriesContext(connection) as captured:
            result = schema.execute_sync(query, context_value=mock_context)

        assert result.errors is None
        return len(captured)

    def test_food_products_query(self, mocker):
        """Test listing food products."""
        user = _create_user("fp1@test.com")
        FoodProduct.objects.create(
            name="Apple", size=150, size_unit="g", num_servings=1, url=""
        )
        FoodProduct.objects.create(
            name="Banana", size=120, size_unit="g", num_servings=1, url=""
        )

        mock_context = mocker.Mock()
        mock_context.request.user = user

        query = "{ foodProducts { id name } }"
        result = schema.execute_sync(query, context_value=mock_context)

        assert result.errors is None
        assert len(result.data["foodProducts"]) == 2
        # ordered by name
        assert result.data["foodProducts"][0]["name"] == "Apple"
        assert result.data["foodProducts"][1]["name"] == "Banana"

    def test_food_products_query_with_servings_has_bounded_query_growth(
        self, mocker
    ):
        """Nested servings queries stop increasing with more products."""
        base_queries = self._count_food_products_with_servings_query(mocker, 2)
        growth_queries = self._count_food_products_with_servings_query(
            mocker, 10
        )

        assert growth_queries == base_queries

    def test_create_food_product(self, mocker):
        """Test creating a food product."""
        user = _create_user("fpcreate@test.com", is_staff=True)
        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation CreateProduct(
                $name: String!, $brand: String, $size: Float!,
                $sizeUnit: String!, $numServings: Float!,
                $energyKcal: Float!, $proteinG: Float!,
                $fatG: Float!, $carbsG: Float!
            ) {
                createFoodProduct(
                    name: $name, brand: $brand,
                    size: $size, sizeUnit: $sizeUnit,
                    numServings: $numServings, energyKcal: $energyKcal,
                    proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG,
                    nutritionalInfoSize: 100.0,
                    nutritionalInfoUnit: "g"
                ) { id name brand }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "name": "Oats",
                "brand": "Quaker",
                "size": 500.0,
                "sizeUnit": "g",
                "numServings": 10.0,
                "energyKcal": 370.0,
                "proteinG": 13.0,
                "fatG": 8.0,
                "carbsG": 60.0,
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["createFoodProduct"]["name"] == "Oats"
        assert result.data["createFoodProduct"]["brand"] == "Quaker"

    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_food_product_write_canonicalizes_equivalent_gtin(
        self, mocker, operation
    ):
        """Product writes persist valid GTINs in their minimal supported form."""
        user = _create_user(f"gtin-{operation}@test.com", is_staff=True)
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(name="Original")
        if operation == "create":
            mutation = """
                mutation CanonicalBarcode($barcode: String) {
                    createFoodProduct(name: "Canonical", barcode: $barcode) {
                        id barcode
                    }
                }
            """
            variables = {"barcode": "00036000291452"}
            result_key = "createFoodProduct"
        else:
            mutation = """
                mutation CanonicalBarcode($id: ID!, $barcode: String) {
                    updateFoodProduct(
                        id: $id, name: "Canonical", barcode: $barcode
                    ) { id barcode }
                }
            """
            variables = {
                "id": str(product.id),
                "barcode": "00036000291452",
            }
            result_key = "updateFoodProduct"

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        product_id = result.data[result_key]["id"]
        assert result.data[result_key]["barcode"] == "036000291452"
        assert FoodProduct.objects.get(pk=product_id).barcode == "036000291452"

    @pytest.mark.parametrize("operation", ["create", "update"])
    @pytest.mark.parametrize(("barcode", "expected"), [(None, None), ("", "")])
    def test_food_product_write_preserves_empty_barcode_semantics(
        self, mocker, operation, barcode, expected
    ):
        """GTIN canonicalization leaves explicit null and blank values unchanged."""
        user = _create_user(
            f"empty-barcode-{operation}-{repr(barcode)}@test.com",
            is_staff=True,
        )
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(
            name="Original", barcode="3017620422003"
        )
        if operation == "create":
            mutation = """
                mutation EmptyBarcode($barcode: String) {
                    createFoodProduct(name: "Empty barcode", barcode: $barcode) {
                        id barcode
                    }
                }
            """
            variables = {"barcode": barcode}
            result_key = "createFoodProduct"
        else:
            mutation = """
                mutation EmptyBarcode($id: ID!, $barcode: String) {
                    updateFoodProduct(
                        id: $id, name: "Empty barcode", barcode: $barcode
                    ) { id barcode }
                }
            """
            variables = {"id": str(product.id), "barcode": barcode}
            result_key = "updateFoodProduct"

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        product_id = result.data[result_key]["id"]
        assert result.data[result_key]["barcode"] == expected
        assert FoodProduct.objects.get(pk=product_id).barcode == expected

    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_food_product_accepts_representable_decimal_boundaries(
        self, mocker, operation
    ):
        """Both product write paths preserve supported one/two-decimal values."""
        user = _create_user(f"fp-boundary-{operation}@test.com", is_staff=True)
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(name="Original")
        arguments = """
            name: "Boundary", nutritionalInfoSize: 0.1,
            nutritionalInfoUnit: "g", size: 99.9, sizeUnit: "g",
            numServings: 0.1, energyKcal: 12.34, proteinG: 23.45,
            fatG: 34.56, carbsG: 45.67, saturatedFatG: 1.23,
            sugarsG: 2.34, fibreG: 3.45, saltG: null
        """
        if operation == "create":
            mutation = (
                f"mutation {{ createFoodProduct({arguments}) {{ id }} }}"
            )
        else:
            mutation = f"""
                mutation UpdateBoundary($id: ID!) {{
                    updateFoodProduct(id: $id, {arguments}) {{ id }}
                }}
            """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(product.id)},
            context_value=context,
        )

        assert result.errors is None
        persisted = FoodProduct.objects.get(
            pk=result.data[
                (
                    "createFoodProduct"
                    if operation == "create"
                    else "updateFoodProduct"
                )
            ]["id"]
        )
        assert (
            persisted.nutritional_info_size,
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
            Decimal("0.1"),
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

    def test_create_food_product_rejects_non_staff_user(self, mocker):
        """A regular user cannot create a shared food product."""
        user = _create_user("fpcreate-regular@test.com")
        mock_context = mocker.Mock()
        mock_context.request.user = user

        result = schema.execute_sync(
            'mutation { createFoodProduct(name: "Shared") { id } }',
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert not FoodProduct.objects.filter(name="Shared").exists()

    def test_create_food_product_rejects_zero_num_servings(self, mocker):
        """A product must contain at least one positive serving fraction."""
        user = _create_user("fp-zero-servings@test.com", is_staff=True)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation {
                createFoodProduct(name: "Invalid", numServings: 0) { id }
            }
        """

        result = schema.execute_sync(mutation, context_value=mock_context)

        assert result.errors is not None
        assert "numServings must be greater than 0" in str(result.errors[0])
        assert not FoodProduct.objects.filter(name="Invalid").exists()

    @pytest.mark.parametrize(
        "nutritional_info_size",
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
    def test_create_food_product_rejects_invalid_nutritional_info_size(
        self, mocker, nutritional_info_size
    ):
        """Creating a product requires a finite positive nutrition basis."""
        user = _create_user(
            f"fp-invalid-nutrition-{repr(nutritional_info_size)}@test.com",
            is_staff=True,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateProduct($nutritionalInfoSize: Float!) {
                createFoodProduct(
                    name: "Invalid nutrition basis",
                    nutritionalInfoSize: $nutritionalInfoSize
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "nutritionalInfoSize": nutritional_info_size,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        if nutritional_info_size in (0.0, -1.0):
            assert "nutritionalInfoSize must be greater than 0" in str(
                result.errors[0]
            )
        assert not FoodProduct.objects.filter(
            name="Invalid nutrition basis"
        ).exists()

    def test_update_food_product(self, mocker):
        """Test updating a food product."""
        user = _create_user("fpupd@test.com", is_staff=True)
        fp = FoodProduct.objects.create(
            name="Milko",
            size=1000,
            size_unit="ml",
            num_servings=4,
            nutritional_info_unit="ml",
            url="",
        )

        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation UpdateProduct($id: ID!, $name: String!) {
                updateFoodProduct(
                    id: $id, name: $name,
                    size: 1000.0, sizeUnit: "ml", numServings: 4.0,
                    nutritionalInfoSize: 100.0,
                    nutritionalInfoUnit: "ml",
                    energyKcal: 50.0, proteinG: 3.5,
                    fatG: 1.5, carbsG: 5.0
                ) { name }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(fp.id), "name": "Milko Lite"},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateFoodProduct"]["name"] == "Milko Lite"

    def test_update_food_product_rejects_non_staff_user(self, mocker):
        """A regular user cannot update a shared food product."""
        user = _create_user("fpupd-regular@test.com")
        product = FoodProduct.objects.create(name="Shared", num_servings=1)
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateProduct($id: ID!) {
                updateFoodProduct(id: $id, name: "Changed") { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(product.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        product.refresh_from_db()
        assert product.name == "Shared"

    def test_update_food_product_rejects_negative_num_servings(self, mocker):
        """Updating a product cannot persist a negative serving count."""
        user = _create_user("fp-negative-servings@test.com", is_staff=True)
        product = FoodProduct.objects.create(
            name="Valid",
            size=100,
            size_unit="g",
            num_servings=4,
            url="",
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateProduct($id: ID!) {
                updateFoodProduct(
                    id: $id, name: "Invalid", numServings: -1
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(product.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "numServings must be greater than 0" in str(result.errors[0])
        product.refresh_from_db()
        assert product.name == "Valid"
        assert product.num_servings == 4

    @pytest.mark.parametrize("operation", ["create", "update"])
    @pytest.mark.parametrize("num_servings", [0.01, 1000000000.0])
    def test_food_product_rejects_unrepresentable_num_servings(
        self, mocker, operation, num_servings
    ):
        """Serving counts must fit the destination field without rounding."""
        user = _create_user(
            f"fp-precision-{operation}-{num_servings}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(name="Original", num_servings=4)
        if operation == "create":
            mutation = """
                mutation InvalidCount($numServings: Float!) {
                    createFoodProduct(
                        name: "Invalid count", numServings: $numServings
                    ) { id }
                }
            """
            variables = {"numServings": num_servings}
        else:
            mutation = """
                mutation InvalidCount($id: ID!, $numServings: Float!) {
                    updateFoodProduct(
                        id: $id, name: "Changed", numServings: $numServings
                    ) { id }
                }
            """
            variables = {"id": str(product.id), "numServings": num_servings}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        assert "numServings exceeds supported precision" in str(
            result.errors[0]
        )
        assert not FoodProduct.objects.filter(name="Invalid count").exists()
        product.refresh_from_db()
        assert (product.name, product.num_servings) == ("Original", 4)

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
    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_food_product_rejects_invalid_size_without_partial_writes(
        self, mocker, operation, size
    ):
        """Product writes require a finite positive package size."""
        user = _create_user(
            f"product-size-{operation}-{repr(size)}@test.com", is_staff=True
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        product = None
        original_product_state = None
        original_servings = None
        if operation == "update":
            product = FoodProduct.objects.create(
                name="Valid product size",
                nutritional_info_size=100,
                nutritional_info_unit="g",
                size=500,
                size_unit="g",
                num_servings=5,
                energy_kcal=200,
                protein_g=20,
            )
            original_product_state = (
                product.name,
                product.size,
                product.size_unit,
                product.num_servings,
                product.energy_kcal,
                product.protein_g,
                product.fat_g,
                product.carbs_g,
            )
            original_servings = list(
                product.servings.order_by("id").values_list(
                    "id",
                    "serving_size",
                    "serving_unit",
                    "energy_kcal",
                    "protein_g",
                    "fat_g",
                    "carbs_g",
                )
            )
            mutation = """
                mutation UpdateProduct($id: ID!, $size: Float!) {
                    updateFoodProduct(
                        id: $id,
                        name: "Partially changed",
                        size: $size,
                        sizeUnit: "oz",
                        numServings: 2,
                        energyKcal: 999,
                        proteinG: 99
                    ) { id }
                }
            """
            variable_values = {"id": str(product.id), "size": size}
        else:
            mutation = """
                mutation CreateProduct($size: Float!) {
                    createFoodProduct(
                        name: "Invalid product size",
                        size: $size,
                        sizeUnit: "oz"
                    ) { id }
                }
            """
            variable_values = {"size": size}

        result = schema.execute_sync(
            mutation,
            variable_values=variable_values,
            context_value=mock_context,
        )

        assert result.errors is not None
        if size in (0.0, -1.0):
            assert "size must be greater than 0" in str(result.errors[0])
        if operation == "create":
            assert not FoodProduct.objects.filter(
                name="Invalid product size"
            ).exists()
        else:
            assert product is not None
            product.refresh_from_db()
            assert (
                product.name,
                product.size,
                product.size_unit,
                product.num_servings,
                product.energy_kcal,
                product.protein_g,
                product.fat_g,
                product.carbs_g,
            ) == original_product_state
            assert (
                list(
                    product.servings.order_by("id").values_list(
                        "id",
                        "serving_size",
                        "serving_unit",
                        "energy_kcal",
                        "protein_g",
                        "fat_g",
                        "carbs_g",
                    )
                )
                == original_servings
            )

    @pytest.mark.parametrize(
        "nutritional_info_size",
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
    def test_update_food_product_rejects_invalid_nutritional_info_size(
        self, mocker, nutritional_info_size
    ):
        """Invalid nutrition bases cannot partially update a product."""
        user = _create_user(
            f"fp-upd-invalid-nutrition-{repr(nutritional_info_size)}@test.com",
            is_staff=True,
        )
        product = FoodProduct.objects.create(
            name="Valid nutrition basis",
            nutritional_info_size=100,
            num_servings=1,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateProduct(
                $id: ID!, $nutritionalInfoSize: Float!
            ) {
                updateFoodProduct(
                    id: $id, name: "Partially changed",
                    nutritionalInfoSize: $nutritionalInfoSize
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(product.id),
                "nutritionalInfoSize": nutritional_info_size,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        if nutritional_info_size in (0.0, -1.0):
            assert "nutritionalInfoSize must be greater than 0" in str(
                result.errors[0]
            )
        product.refresh_from_db()
        assert product.name == "Valid nutrition basis"
        assert product.nutritional_info_size == 100

    def test_update_food_product_preserves_omitted_url(self, mocker):
        """Updating unrelated fields preserves the existing product URL."""
        user = _create_user("fp-url@test.com", is_staff=True)
        fp = FoodProduct.objects.create(
            name="Milk",
            size=1000,
            size_unit="ml",
            num_servings=4,
            nutritional_info_unit="ml",
            url="https://example.com/milk",
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateProduct($id: ID!, $name: String!) {
                updateFoodProduct(
                    id: $id, name: $name,
                    size: 1000.0, sizeUnit: "ml", numServings: 4.0,
                    nutritionalInfoSize: 100.0,
                    nutritionalInfoUnit: "ml",
                    energyKcal: 50.0, proteinG: 3.5,
                    fatG: 1.5, carbsG: 5.0
                ) { name url }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(fp.id), "name": "Milk Lite"},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["updateFoodProduct"]["url"] == (
            "https://example.com/milk"
        )
        fp.refresh_from_db()
        assert fp.url == "https://example.com/milk"

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
    def test_food_product_rejects_invalid_nutrients_without_partial_writes(
        self, mocker, operation, field_name, value
    ):
        """Every exposed product nutrient is finite and non-negative."""
        user = _create_user(
            f"product-nutrient-{operation}-{field_name}-{repr(value)}@test.com",
            is_staff=True,
        )
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(
            name="Original nutrients",
            energy_kcal=100,
            protein_g=10,
            fat_g=5,
            carbs_g=15,
            saturated_fat_g=2,
            sugar_carbs_g=3,
            fibre_carbs_g=4,
            salt_g=1,
        )
        original_count = FoodProduct.objects.count()
        original_state = tuple(
            getattr(product, field)
            for field in (
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
        )
        original_servings = list(
            product.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        if operation == "create":
            mutation = f"""
                mutation InvalidNutrient($value: Float!) {{
                    createFoodProduct(
                        name: "Invalid product nutrient", {field_name}: $value
                    ) {{ id }}
                }}
            """
            variables = {"value": value}
        else:
            mutation = f"""
                mutation InvalidNutrient($id: ID!, $value: Float!) {{
                    updateFoodProduct(
                        id: $id, name: "Changed", {field_name}: $value
                    ) {{ id }}
                }}
            """
            variables = {"id": str(product.id), "value": value}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        if value == -0.1:
            assert f"{field_name} must be greater than or equal to 0" in str(
                result.errors[0]
            )
        assert FoodProduct.objects.count() == original_count
        product.refresh_from_db()
        assert (
            tuple(
                getattr(product, field)
                for field in (
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
            )
            == original_state
        )
        assert (
            list(
                product.servings.order_by("id").values_list(
                    "id", "serving_size", "serving_unit", "energy_kcal"
                )
            )
            == original_servings
        )

    @pytest.mark.parametrize("operation", ["create", "update"])
    @pytest.mark.parametrize("field_name", ["nutritionalInfoUnit", "sizeUnit"])
    def test_food_product_rejects_unsupported_units_before_signals(
        self, mocker, operation, field_name
    ):
        """Product units must be canonical before product signals can run."""
        user = _create_user(
            f"product-unit-{operation}-{field_name}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(name="Original unit")
        original_count = FoodProduct.objects.count()
        original_state = (
            product.name,
            product.nutritional_info_unit,
            product.size_unit,
        )
        original_servings = list(
            product.servings.order_by("id").values_list(
                "id", "serving_size", "serving_unit", "energy_kcal"
            )
        )
        if operation == "create":
            mutation = f"""
                mutation {{
                    createFoodProduct(
                        name: "Invalid product unit", {field_name}: "unsupported"
                    ) {{ id }}
                }}
            """
            variables = None
        else:
            mutation = f"""
                mutation InvalidUnit($id: ID!) {{
                    updateFoodProduct(
                        id: $id, name: "Changed", {field_name}: "unsupported"
                    ) {{ id }}
                }}
            """
            variables = {"id": str(product.id)}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        assert f"{field_name} must be a supported unit" in str(
            result.errors[0]
        )
        assert FoodProduct.objects.count() == original_count
        product.refresh_from_db()
        assert (
            product.name,
            product.nutritional_info_unit,
            product.size_unit,
        ) == (original_state)
        assert (
            list(
                product.servings.order_by("id").values_list(
                    "id", "serving_size", "serving_unit", "energy_kcal"
                )
            )
            == original_servings
        )

    def test_delete_food_product(self, mocker):
        """Test deleting a food product."""
        user = _create_user("fpdel@test.com", is_staff=True)
        fp = FoodProduct.objects.create(
            name="Bread", size=500, size_unit="g", num_servings=10, url=""
        )

        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = (
            "mutation DeleteProduct($id: ID!) { deleteFoodProduct(id: $id) }"
        )
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(fp.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["deleteFoodProduct"] is True
        assert not FoodProduct.objects.filter(pk=fp.id).exists()

    def test_delete_food_product_rejects_non_staff_user(self, mocker):
        """A regular user cannot delete a shared food product."""
        user = _create_user("fpdel-regular@test.com")
        fp = FoodProduct.objects.create(
            name="Shared Bread",
            size=500,
            size_unit="g",
            num_servings=10,
            url="",
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = (
            "mutation DeleteProduct($id: ID!) { deleteFoodProduct(id: $id) }"
        )

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(fp.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert FoodProduct.objects.filter(pk=fp.id).exists()


@pytest.mark.django_db
class TestServingSchema:
    """Tests for Serving mutations."""

    def test_create_serving(self, mocker):
        """Test creating a serving."""
        user = _create_user("srvcreate@test.com", is_staff=True)
        fp = FoodProduct.objects.create(
            name="Peanut Butter",
            size=500,
            size_unit="g",
            num_servings=30,
            nutritional_info_size=100,
            nutritional_info_unit="g",
            energy_kcal=600,
            protein_g=25,
            url="",
        )

        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation CreateServing(
                $foodId: ID!, $servingSize: Float!, $servingUnit: String!
            ) {
                createServing(
                    foodId: $foodId, servingSize: $servingSize,
                    servingUnit: $servingUnit
                ) {
                    servingSize servingUnit energyKcal
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "foodId": str(fp.id),
                "servingSize": 15.0,
                "servingUnit": "g",
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["createServing"]["servingSize"] == 15.0
        # 100g = 600kcal -> 15g = 90kcal
        assert result.data["createServing"]["energyKcal"] == 90.0

    @pytest.mark.parametrize(
        ("operation", "serving_size"), [("create", 0.1), ("update", 99.9)]
    )
    def test_serving_accepts_one_decimal_boundaries(
        self, mocker, operation, serving_size
    ):
        """Serving create and update preserve supported one-decimal boundaries."""
        user = _create_user(
            f"serving-boundary-{operation}@test.com", is_staff=True
        )
        product = FoodProduct.objects.create(name=f"Boundary {operation}")
        serving = product.servings.get(serving_size=100, serving_unit="g")
        context = mocker.Mock()
        context.request.user = user
        if operation == "create":
            mutation = """
                mutation Boundary($foodId: ID!, $servingSize: Float!) {
                    createServing(
                        foodId: $foodId, servingSize: $servingSize,
                        servingUnit: "g"
                    ) { id }
                }
            """
            variables = {
                "foodId": str(product.id),
                "servingSize": serving_size,
            }
        else:
            mutation = """
                mutation Boundary($id: ID!, $servingSize: Float!) {
                    updateServing(
                        id: $id, servingSize: $servingSize, servingUnit: "g"
                    ) { id }
                }
            """
            variables = {"id": str(serving.id), "servingSize": serving_size}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        persisted = Serving.objects.get(
            pk=result.data[
                "createServing" if operation == "create" else "updateServing"
            ]["id"]
        )
        assert persisted.serving_size == Decimal(str(serving_size))

    def test_create_serving_rejects_non_staff_user(self, mocker):
        """A regular user cannot create a shared serving."""
        user = _create_user("srvcreate-regular@test.com")
        product = FoodProduct.objects.create(name="Shared", num_servings=1)
        initial_count = product.servings.count()
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateServing($foodId: ID!) {
                createServing(
                    foodId: $foodId, servingSize: 25, servingUnit: "g"
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"foodId": str(product.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert product.servings.count() == initial_count

    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_serving_rejects_unsupported_unit_without_partial_writes(
        self, mocker, operation
    ):
        """Serving units are checked against the canonical model choices."""
        user = _create_user(
            f"serving-unit-{operation}@test.com", is_staff=True
        )
        context = mocker.Mock()
        context.request.user = user
        product = FoodProduct.objects.create(name=f"Serving unit {operation}")
        serving = product.servings.get(serving_size=100, serving_unit="g")
        original_ids = set(product.servings.values_list("id", flat=True))
        original_state = (
            serving.serving_size,
            serving.serving_unit,
            serving.energy_kcal,
        )
        if operation == "create":
            mutation = """
                mutation InvalidUnit($foodId: ID!) {
                    createServing(
                        foodId: $foodId, servingSize: 10,
                        servingUnit: "unsupported"
                    ) { id }
                }
            """
            variables = {"foodId": str(product.id)}
        else:
            mutation = """
                mutation InvalidUnit($id: ID!) {
                    updateServing(
                        id: $id, servingSize: 10,
                        servingUnit: "unsupported"
                    ) { id }
                }
            """
            variables = {"id": str(serving.id)}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is not None
        assert "servingUnit must be a supported unit" in str(result.errors[0])
        assert (
            set(product.servings.values_list("id", flat=True)) == original_ids
        )
        serving.refresh_from_db()
        assert (
            serving.serving_size,
            serving.serving_unit,
            serving.energy_kcal,
        ) == original_state

    @pytest.mark.parametrize(
        "serving_size",
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
    @pytest.mark.parametrize("operation", ["create", "update"])
    def test_serving_rejects_invalid_size_without_partial_writes(
        self, mocker, operation, serving_size
    ):
        """Serving writes require a finite positive size before persistence."""
        user = _create_user(
            f"serving-invalid-{operation}-{repr(serving_size)}@test.com",
            is_staff=True,
        )
        product = FoodProduct.objects.create(
            name=f"Serving validation {operation} {repr(serving_size)}",
            size=500,
            size_unit="g",
            num_servings=5,
            nutritional_info_size=100,
            nutritional_info_unit="g",
            energy_kcal=200,
            protein_g=20,
        )
        existing_ids = set(product.servings.values_list("id", flat=True))
        serving = product.servings.get(serving_size=100, serving_unit="g")
        original_state = (
            serving.serving_size,
            serving.serving_unit,
            serving.energy_kcal,
            serving.protein_g,
            serving.fat_g,
            serving.carbs_g,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        if operation == "create":
            mutation = """
                mutation CreateServing($foodId: ID!, $servingSize: Float!) {
                    createServing(
                        foodId: $foodId,
                        servingSize: $servingSize,
                        servingUnit: "oz"
                    ) { id }
                }
            """
            variable_values = {
                "foodId": str(product.id),
                "servingSize": serving_size,
            }
        else:
            mutation = """
                mutation UpdateServing($id: ID!, $servingSize: Float!) {
                    updateServing(
                        id: $id,
                        servingSize: $servingSize,
                        servingUnit: "oz"
                    ) { id }
                }
            """
            variable_values = {
                "id": str(serving.id),
                "servingSize": serving_size,
            }

        result = schema.execute_sync(
            mutation,
            variable_values=variable_values,
            context_value=mock_context,
        )

        assert result.errors is not None
        if serving_size in (0.0, -1.0):
            assert "servingSize must be greater than 0" in str(
                result.errors[0]
            )
        assert (
            set(product.servings.values_list("id", flat=True)) == existing_ids
        )
        serving.refresh_from_db()
        assert (
            serving.serving_size,
            serving.serving_unit,
            serving.energy_kcal,
            serving.protein_g,
            serving.fat_g,
            serving.carbs_g,
        ) == original_state

    def test_update_serving(self, mocker):
        """Test updating a serving."""
        user = _create_user("srvupd@test.com", is_staff=True)
        fp = FoodProduct.objects.create(
            name="Peanut Butter",
            size=500,
            size_unit="g",
            num_servings=30,
            nutritional_info_size=100,
            nutritional_info_unit="g",
            energy_kcal=600,
            protein_g=25,
            url="",
        )
        srv = Serving.objects.create(
            food=fp, serving_size=15, serving_unit="g"
        )

        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = """
            mutation UpdateServing(
                $id: ID!, $servingSize: Float!, $servingUnit: String!
            ) {
                updateServing(
                    id: $id, servingSize: $servingSize,
                    servingUnit: $servingUnit
                ) {
                    energyKcal
                }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(srv.id),
                "servingSize": 30.0,
                "servingUnit": "g",
            },
            context_value=mock_context,
        )

        assert result.errors is None
        # 100g = 600kcal -> 30g = 180kcal
        assert result.data["updateServing"]["energyKcal"] == 180.0

    def test_update_serving_rejects_non_staff_user(self, mocker):
        """A regular user cannot update a shared serving."""
        user = _create_user("srvupd-regular@test.com")
        product = FoodProduct.objects.create(name="Shared", num_servings=1)
        serving = product.servings.first()
        original_size = serving.serving_size
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateServing($id: ID!) {
                updateServing(id: $id, servingSize: 25, servingUnit: "g") {
                    id
                }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(serving.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        serving.refresh_from_db()
        assert serving.serving_size == original_size

    def test_delete_serving(self, mocker):
        """Test deleting a serving."""
        user = _create_user("srvdel@test.com", is_staff=True)
        fp = FoodProduct.objects.create(
            name="Bread", size=500, size_unit="g", num_servings=10, url=""
        )
        srv = Serving.objects.create(
            food=fp, serving_size=50, serving_unit="g"
        )

        mock_context = mocker.Mock()
        mock_context.request.user = user

        mutation = (
            "mutation DeleteServing($id: ID!) { deleteServing(id: $id) }"
        )
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(srv.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["deleteServing"] is True
        assert not Serving.objects.filter(pk=srv.id).exists()

    def test_delete_serving_rejects_non_staff_user(self, mocker):
        """A regular user cannot delete from the shared serving catalog."""
        user = _create_user("srvdel-regular@test.com")
        fp = FoodProduct.objects.create(
            name="Shared Bread",
            size=500,
            size_unit="g",
            num_servings=10,
            url="",
        )
        srv = fp.servings.first()
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = (
            "mutation DeleteServing($id: ID!) { deleteServing(id: $id) }"
        )

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(srv.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Staff access required" in str(result.errors[0])
        assert Serving.objects.filter(pk=srv.id).exists()
