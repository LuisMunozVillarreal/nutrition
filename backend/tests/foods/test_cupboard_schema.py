"""Tests for Cupboard GraphQL schema."""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.foods.models import CupboardItem, FoodProduct
from config.schema import schema

User = get_user_model()


def _create_user(email):
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


@pytest.mark.django_db
class TestCupboardSchema:
    """Tests for Cupboard mutations and queries."""

    def test_cupboard_items_query(self, mocker):
        """Test listing cupboard items."""
        # Given an authenticated user and some cupboard items
        user = _create_user("cq@test.com")
        fp = FoodProduct.objects.create(
            name="Milk", size=1000, size_unit="ml", num_servings=4
        )
        CupboardItem.objects.create(
            food=fp, purchased_at=timezone.now(), consumed_perc=0
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When querying cupboard items
        query = "{ cupboardItems { id foodLabel consumedPerc } }"
        result = schema.execute_sync(query, context_value=mock_context)

        # Then the result contains the item
        assert result.errors is None
        assert len(result.data["cupboardItems"]) == 1
        assert "Milk" in result.data["cupboardItems"][0]["foodLabel"]

    def test_create_cupboard_item(self, mocker):
        """Test creating a cupboard item."""
        # Given an authenticated user and a food product
        user = _create_user("cc@test.com")
        fp = FoodProduct.objects.create(
            name="Eggs", size=6, size_unit="count", num_servings=6
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When creating a cupboard item
        mutation = """
            mutation CreateItem($foodId: ID!, $purchasedAt: String!) {
                createCupboardItem(
                    foodId: $foodId, purchasedAt: $purchasedAt,
                    consumedPerc: 0
                ) { id foodLabel }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={
                "foodId": str(fp.id),
                "purchasedAt": timezone.now().isoformat(),
            },
            context_value=mock_context,
        )

        # Then the item is created
        assert result.errors is None
        assert "Eggs" in result.data["createCupboardItem"]["foodLabel"]
        assert CupboardItem.objects.filter(food=fp).exists()

    def test_update_cupboard_item(self, mocker):
        """Test updating a cupboard item's consumption."""
        # Given an authenticated user and a cupboard item
        user = _create_user("cu@test.com")
        fp = FoodProduct.objects.create(
            name="Bread", size=500, size_unit="g", num_servings=10
        )
        item = CupboardItem.objects.create(
            food=fp, purchased_at=timezone.now(), consumed_perc=0
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When updating the consumed percentage
        mutation = """
            mutation UpdateItem($id: ID!, $consumedPerc: Float!) {
                updateCupboardItem(
                    id: $id, consumedPerc: $consumedPerc
                ) { consumedPerc started finished }
            }
        """
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id), "consumedPerc": 50.0},
            context_value=mock_context,
        )

        # Then the item is updated and started is True
        assert result.errors is None
        assert result.data["updateCupboardItem"]["consumedPerc"] == 50.0
        assert result.data["updateCupboardItem"]["started"] is True
        assert result.data["updateCupboardItem"]["finished"] is False

    def test_delete_cupboard_item(self, mocker):
        """Test deleting a cupboard item."""
        # Given an authenticated user and a cupboard item
        user = _create_user("cdel@test.com")
        fp = FoodProduct.objects.create(
            name="Rice", size=1000, size_unit="g", num_servings=10
        )
        item = CupboardItem.objects.create(
            food=fp, purchased_at=timezone.now()
        )

        # And a mock context
        mock_context = mocker.Mock()
        mock_context.request.user = user

        # When deleting the item
        mutation = (
            "mutation DeleteItem($id: ID!) { deleteCupboardItem(id: $id) }"
        )
        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id)},
            context_value=mock_context,
        )

        # Then the item is deleted
        assert result.errors is None
        assert result.data["deleteCupboardItem"] is True
        assert not CupboardItem.objects.filter(pk=item.id).exists()
