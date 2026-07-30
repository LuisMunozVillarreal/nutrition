"""Tests for FoodProducts and Servings GraphQL schema."""

import pytest
from django.contrib.auth import get_user_model

from apps.foods.models import FoodProduct, Serving
from apps.foods.schema import _validated_product_num_servings
from config.schema import schema

User = get_user_model()


@pytest.mark.parametrize(
    "num_servings", [float("nan"), float("inf"), -float("inf")]
)
def test_product_num_servings_must_be_finite(num_servings):
    """Non-finite product serving counts are rejected."""
    with pytest.raises(ValueError, match="numServings must be greater than 0"):
        _validated_product_num_servings(num_servings)


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

    def test_create_food_product(self, mocker):
        """Test creating a food product."""
        user = _create_user("fpcreate@test.com")
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

    def test_create_food_product_rejects_zero_num_servings(self, mocker):
        """A product must contain at least one positive serving fraction."""
        user = _create_user("fp-zero-servings@test.com")
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

    def test_update_food_product(self, mocker):
        """Test updating a food product."""
        user = _create_user("fpupd@test.com")
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

    def test_update_food_product_rejects_negative_num_servings(self, mocker):
        """Updating a product cannot persist a negative serving count."""
        user = _create_user("fp-negative-servings@test.com")
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

    def test_update_food_product_preserves_omitted_url(self, mocker):
        """Updating unrelated fields preserves the existing product URL."""
        user = _create_user("fp-url@test.com")
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
        user = _create_user("srvcreate@test.com")
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

    def test_update_serving(self, mocker):
        """Test updating a serving."""
        user = _create_user("srvupd@test.com")
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
