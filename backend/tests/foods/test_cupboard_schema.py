"""Tests for Cupboard GraphQL schema."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.foods.models import (
    CupboardItem,
    CupboardItemConsumption,
    FoodProduct,
    Recipe,
    RecipeIngredient,
    Serving,
)
from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
    get_linked_consumed_perc,
)
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
        other_user = _create_user("cq-other@test.com")
        fp = FoodProduct.objects.create(
            name="Milk", size=1000, size_unit="ml", num_servings=4
        )
        CupboardItem.objects.create(
            owner=user,
            food=fp,
            purchased_at=timezone.now(),
            consumed_perc=0,
        )
        CupboardItem.objects.create(
            owner=other_user,
            food=fp,
            purchased_at=timezone.now(),
            consumed_perc=50,
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
        item = CupboardItem.objects.get(food=fp)
        assert item.owner == user

    @pytest.mark.parametrize(
        ("operation", "consumed_perc"), [("create", 0.01), ("update", 99.99)]
    )
    def test_cupboard_item_accepts_two_decimal_boundaries(
        self, mocker, operation, consumed_perc
    ):
        """Cupboard create and update preserve supported two-decimal values."""
        user = _create_user(f"cupboard-boundary-{operation}@test.com")
        product = FoodProduct.objects.create(name=f"Boundary {operation}")
        item = CupboardItem.objects.create(
            owner=user,
            food=product,
            purchased_at=timezone.now(),
            consumed_perc=Decimal("0.01"),
        )
        context = mocker.Mock()
        context.request.user = user
        if operation == "create":
            item.delete()
            mutation = """
                mutation Boundary(
                    $foodId: ID!, $purchasedAt: String!, $consumedPerc: Float!
                ) {
                    createCupboardItem(
                        foodId: $foodId, purchasedAt: $purchasedAt,
                        consumedPerc: $consumedPerc
                    ) { id }
                }
            """
            variables = {
                "foodId": str(product.id),
                "purchasedAt": timezone.now().isoformat(),
                "consumedPerc": consumed_perc,
            }
        else:
            mutation = """
                mutation Boundary($id: ID!, $consumedPerc: Float!) {
                    updateCupboardItem(
                        id: $id, consumedPerc: $consumedPerc
                    ) { id }
                }
            """
            variables = {"id": str(item.id), "consumedPerc": consumed_perc}

        result = schema.execute_sync(
            mutation, variable_values=variables, context_value=context
        )

        assert result.errors is None
        persisted = CupboardItem.objects.get(
            pk=result.data[
                (
                    "createCupboardItem"
                    if operation == "create"
                    else "updateCupboardItem"
                )
            ]["id"]
        )
        assert persisted.consumed_perc == Decimal(str(consumed_perc))
        assert persisted.manual_consumed_perc == Decimal(str(consumed_perc))

    def test_cupboard_item_detail_hides_another_users_item(self, mocker):
        """A user cannot read another user's cupboard item detail."""
        user = _create_user("detail@test.com")
        other_user = _create_user("detail-other@test.com")
        fp = FoodProduct.objects.create(name="Private", num_servings=1)
        item = CupboardItem.objects.create(
            owner=other_user,
            food=fp,
            purchased_at=timezone.now(),
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        query = "query Item($id: ID!) { cupboardItem(id: $id) { id } }"

        result = schema.execute_sync(
            query,
            variable_values={"id": str(item.id)},
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["cupboardItem"] is None

    def test_create_cupboard_item_from_recipe(self, mocker):
        """Test creating a cupboard item from a recipe base food ID."""
        user = _create_user("recipe-cupboard@test.com")
        recipe = Recipe.objects.create(
            name="Soup", size=4, size_unit="count", num_servings=4
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user

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
                "foodId": str(recipe.food_ptr_id),
                "purchasedAt": timezone.now().isoformat(),
            },
            context_value=mock_context,
        )

        assert result.errors is None
        assert "Soup" in result.data["createCupboardItem"]["foodLabel"]
        assert CupboardItem.objects.filter(food_id=recipe.food_ptr_id).exists()

    def test_create_cooked_recipe_overconsumption_rolls_back_everything(
        self, mocker
    ):
        """Failed cooking leaves recipe and all ingredient stocks unchanged."""
        user = _create_user("recipe-cupboard-atomic@test.com")
        first_product = FoodProduct.objects.create(
            name="First ingredient",
            size=400,
            size_unit="g",
            num_servings=4,
        )
        second_product = FoodProduct.objects.create(
            name="Second ingredient",
            size=400,
            size_unit="g",
            num_servings=4,
        )
        first_serving = first_product.servings.get(
            serving_size=100, serving_unit="g"
        )
        oversized_second_serving = Serving.objects.create(
            food=second_product,
            serving_size=200,
            serving_unit="g",
        )
        first_item = CupboardItem.objects.create(
            owner=user,
            food=first_product,
            purchased_at=timezone.now(),
        )
        second_item = CupboardItem.objects.create(
            owner=user,
            food=second_product,
            purchased_at=timezone.now(),
            consumed_perc=75,
        )
        recipe = Recipe.objects.create(
            name="Atomic recipe", size=1, size_unit="count", num_servings=1
        )
        RecipeIngredient.objects.create(
            recipe=recipe, food=first_serving, num_servings=1
        )
        RecipeIngredient.objects.create(
            recipe=recipe, food=oversized_second_serving, num_servings=1
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateItem($foodId: ID!, $purchasedAt: String!) {
                createCupboardItem(
                    foodId: $foodId,
                    purchasedAt: $purchasedAt,
                    consumedPerc: 0
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "foodId": str(recipe.food_ptr_id),
                "purchasedAt": timezone.now().isoformat(),
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        assert isinstance(
            result.errors[0].original_error,
            CupboardItemConsumptionTooBigError,
        )
        first_item.refresh_from_db()
        second_item.refresh_from_db()
        assert not CupboardItem.objects.filter(
            owner=user, food_id=recipe.food_ptr_id
        ).exists()
        assert first_item.consumed_perc == 0
        assert second_item.consumed_perc == 75
        assert not CupboardItemConsumption.objects.filter(
            item__in=[first_item, second_item]
        ).exists()

    def test_update_cupboard_item(self, mocker):
        """Test updating a cupboard item's consumption."""
        # Given an authenticated user and a cupboard item
        user = _create_user("cu@test.com")
        fp = FoodProduct.objects.create(
            name="Bread", size=500, size_unit="g", num_servings=10
        )
        item = CupboardItem.objects.create(
            owner=user,
            food=fp,
            purchased_at=timezone.now(),
            consumed_perc=0,
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

    def test_update_cupboard_item_locks_authoritative_row(self, mocker):
        """Manual totals lock the cupboard row before deriving their baseline."""
        user = _create_user("cupboard-manual-lock@test.com")
        product = FoodProduct.objects.create(
            name="Locked product", size=400, size_unit="g", num_servings=4
        )
        item = CupboardItem.objects.create(
            owner=user, food=product, purchased_at=timezone.now()
        )
        context = mocker.Mock()
        context.request.user = user
        lock = mocker.spy(CupboardItem.objects, "select_for_update")

        def read_links_after_lock(authoritative_item):
            assert lock.call_count == 1
            return get_linked_consumed_perc(authoritative_item)

        mocker.patch(
            "apps.foods.schema.get_linked_consumed_perc",
            side_effect=read_links_after_lock,
        )

        result = schema.execute_sync(
            """
            mutation UpdateItem($id: ID!) {
                updateCupboardItem(id: $id, consumedPerc: 40) {
                    consumedPerc
                }
            }
            """,
            variable_values={"id": str(item.id)},
            context_value=context,
        )

        assert result.errors is None
        assert result.data["updateCupboardItem"]["consumedPerc"] == 40
        lock.assert_called_once_with()

    def test_update_cupboard_item_rolls_back_manual_write_on_failure(
        self, mocker
    ):
        """Manual baseline and total commit as one atomic update."""
        user = _create_user("cupboard-manual-rollback@test.com")
        product = FoodProduct.objects.create(
            name="Rollback product", size=400, size_unit="g", num_servings=4
        )
        item = CupboardItem.objects.create(
            owner=user,
            food=product,
            purchased_at=timezone.now(),
            consumed_perc=Decimal("20"),
        )
        context = mocker.Mock()
        context.request.user = user
        mocker.patch(
            "apps.foods.schema.recalculate_consumed_perc",
            side_effect=RuntimeError("injected recalculation failure"),
        )

        result = schema.execute_sync(
            """
            mutation UpdateItem($id: ID!) {
                updateCupboardItem(id: $id, consumedPerc: 40) {
                    consumedPerc
                }
            }
            """,
            variable_values={"id": str(item.id)},
            context_value=context,
        )

        assert result.errors is not None
        assert "injected recalculation failure" in str(result.errors[0])
        item.refresh_from_db()
        assert item.manual_consumed_perc == Decimal("20")
        assert item.consumed_perc == Decimal("20")

    def test_update_cupboard_item_keeps_linked_only_total_unchanged(
        self, mocker
    ):
        """Saving a linked-only displayed total does not double-count linked use."""
        user = _create_user("cupboard-linked-total@test.com")
        product = FoodProduct.objects.create(
            name="Linked product", size=400, size_unit="g", num_servings=4
        )
        item = CupboardItem.objects.create(
            owner=user, food=product, purchased_at=timezone.now()
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        CupboardItemConsumption.objects.create(item=item, serving=serving)
        context = mocker.Mock()
        context.request.user = user
        mutation = """
            mutation UpdateItem($id: ID!, $consumedPerc: Float!) {
                updateCupboardItem(id: $id, consumedPerc: $consumedPerc) {
                    consumedPerc
                }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id), "consumedPerc": 25.0},
            context_value=context,
        )

        assert result.errors is None
        assert result.data["updateCupboardItem"]["consumedPerc"] == 25
        item.refresh_from_db()
        assert item.manual_consumed_perc == 0
        assert item.consumed_perc == 25

    def test_update_cupboard_item_keeps_mixed_total_unchanged(self, mocker):
        """Saving a mixed displayed total preserves its manual baseline."""
        user = _create_user("cupboard-manual-baseline@test.com")
        product = FoodProduct.objects.create(
            name="Baseline product", size=400, size_unit="g", num_servings=4
        )
        item = CupboardItem.objects.create(
            owner=user,
            food=product,
            purchased_at=timezone.now(),
            consumed_perc=20,
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        CupboardItemConsumption.objects.create(item=item, serving=serving)
        context = mocker.Mock()
        context.request.user = user
        mutation = """
            mutation UpdateItem($id: ID!) {
                updateCupboardItem(id: $id, consumedPerc: 45) {
                    consumedPerc
                }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id)},
            context_value=context,
        )

        assert result.errors is None
        assert result.data["updateCupboardItem"]["consumedPerc"] == 45
        item.refresh_from_db()
        assert item.manual_consumed_perc == 20
        assert item.consumed_perc == 45

    def test_update_cupboard_item_changes_total_and_recalculates_later_use(
        self, mocker
    ):
        """A changed displayed total becomes a baseline for later linked use."""
        user = _create_user("cupboard-changed-total@test.com")
        product = FoodProduct.objects.create(
            name="Changing product", size=400, size_unit="g", num_servings=4
        )
        item = CupboardItem.objects.create(
            owner=user,
            food=product,
            purchased_at=timezone.now(),
            consumed_perc=20,
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        CupboardItemConsumption.objects.create(item=item, serving=serving)
        context = mocker.Mock()
        context.request.user = user
        mutation = """
            mutation UpdateItem($id: ID!) {
                updateCupboardItem(id: $id, consumedPerc: 60) {
                    consumedPerc
                }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id)},
            context_value=context,
        )

        assert result.errors is None
        item.refresh_from_db()
        assert item.manual_consumed_perc == 35
        assert item.consumed_perc == 60

        CupboardItemConsumption.objects.create(item=item, serving=serving)

        item.refresh_from_db()
        assert item.manual_consumed_perc == 35
        assert item.consumed_perc == 85

    def test_update_cupboard_item_rejects_total_below_linked_use(self, mocker):
        """A displayed total cannot be lower than immutable linked consumption."""
        user = _create_user("cupboard-below-linked@test.com")
        product = FoodProduct.objects.create(
            name="Linked floor product",
            size=400,
            size_unit="g",
            num_servings=4,
        )
        item = CupboardItem.objects.create(
            owner=user, food=product, purchased_at=timezone.now()
        )
        serving = product.servings.get(serving_size=100, serving_unit="g")
        CupboardItemConsumption.objects.create(item=item, serving=serving)
        context = mocker.Mock()
        context.request.user = user
        mutation = """
            mutation UpdateItem($id: ID!) {
                updateCupboardItem(id: $id, consumedPerc: 24.9) {
                    consumedPerc
                }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id)},
            context_value=context,
        )

        assert result.errors is not None
        assert "consumedPerc cannot be less than linked consumption" in str(
            result.errors[0]
        )
        item.refresh_from_db()
        assert item.manual_consumed_perc == 0
        assert item.consumed_perc == 25

    def test_update_cupboard_item_rejects_another_user(self, mocker):
        """A user cannot update another user's cupboard item."""
        user = _create_user("update-private@test.com")
        other_user = _create_user("update-private-other@test.com")
        fp = FoodProduct.objects.create(name="Private", num_servings=1)
        item = CupboardItem.objects.create(
            owner=other_user,
            food=fp,
            purchased_at=timezone.now(),
            consumed_perc=25,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateItem($id: ID!) {
                updateCupboardItem(id: $id, consumedPerc: 50) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Item not found" in str(result.errors[0])
        item.refresh_from_db()
        assert item.consumed_perc == 25

    @pytest.mark.parametrize(
        "consumed_perc",
        [
            -0.1,
            0.001,
            99.999,
            100.1,
            float("nan"),
            float("inf"),
            -float("inf"),
        ],
    )
    def test_create_cupboard_item_rejects_out_of_range_consumption(
        self, mocker, consumed_perc
    ):
        """Creating an item rejects percentages outside zero to one hundred."""
        user = _create_user(f"cc-invalid-{consumed_perc}@test.com")
        fp = FoodProduct.objects.create(
            name="Invalid Eggs", size=6, size_unit="count", num_servings=6
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation CreateItem(
                $foodId: ID!, $purchasedAt: String!, $consumedPerc: Float!
            ) {
                createCupboardItem(
                    foodId: $foodId, purchasedAt: $purchasedAt,
                    consumedPerc: $consumedPerc
                ) { id }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "foodId": str(fp.id),
                "purchasedAt": timezone.now().isoformat(),
                "consumedPerc": consumed_perc,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        if consumed_perc in (-0.1, 100.1):
            assert "consumedPerc must be between 0 and 100" in str(
                result.errors[0]
            )
        assert not CupboardItem.objects.filter(food=fp).exists()

    @pytest.mark.parametrize(
        "consumed_perc",
        [
            -0.1,
            0.001,
            99.999,
            100.1,
            float("nan"),
            float("inf"),
            -float("inf"),
        ],
    )
    def test_update_cupboard_item_rejects_out_of_range_consumption(
        self, mocker, consumed_perc
    ):
        """Updating an item rejects percentages outside zero to one hundred."""
        user = _create_user(f"cu-invalid-{consumed_perc}@test.com")
        fp = FoodProduct.objects.create(
            name="Invalid Bread", size=500, size_unit="g", num_servings=10
        )
        item = CupboardItem.objects.create(
            owner=user,
            food=fp,
            purchased_at=timezone.now(),
            consumed_perc=25,
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = """
            mutation UpdateItem($id: ID!, $consumedPerc: Float!) {
                updateCupboardItem(
                    id: $id, consumedPerc: $consumedPerc
                ) { consumedPerc }
            }
        """

        result = schema.execute_sync(
            mutation,
            variable_values={
                "id": str(item.id),
                "consumedPerc": consumed_perc,
            },
            context_value=mock_context,
        )

        assert result.errors is not None
        if consumed_perc in (-0.1, 100.1):
            assert "consumedPerc must be between 0 and 100" in str(
                result.errors[0]
            )
        item.refresh_from_db()
        assert item.consumed_perc == 25

    def test_delete_cupboard_item(self, mocker):
        """Test deleting a cupboard item."""
        # Given an authenticated user and a cupboard item
        user = _create_user("cdel@test.com")
        fp = FoodProduct.objects.create(
            name="Rice", size=1000, size_unit="g", num_servings=10
        )
        item = CupboardItem.objects.create(
            owner=user, food=fp, purchased_at=timezone.now()
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

    def test_delete_cupboard_item_rejects_another_user(self, mocker):
        """A user cannot delete another user's cupboard item."""
        user = _create_user("delete-private@test.com")
        other_user = _create_user("delete-private-other@test.com")
        fp = FoodProduct.objects.create(name="Private", num_servings=1)
        item = CupboardItem.objects.create(
            owner=other_user,
            food=fp,
            purchased_at=timezone.now(),
        )
        mock_context = mocker.Mock()
        mock_context.request.user = user
        mutation = (
            "mutation DeleteItem($id: ID!) { deleteCupboardItem(id: $id) }"
        )

        result = schema.execute_sync(
            mutation,
            variable_values={"id": str(item.id)},
            context_value=mock_context,
        )

        assert result.errors is not None
        assert "Item not found" in str(result.errors[0])
        assert CupboardItem.objects.filter(pk=item.id).exists()
