"""Tests for food product barcode lookup GraphQL schema."""

import pytest
import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.foods.models import FoodProduct, Serving
from config.schema import schema

User = get_user_model()

BARCODE = "3017620422003"
OFF_PRODUCT_PAGE = "https://world.openfoodfacts.org/product/3017620422003"


def _create_user(email: str):
    """Create a user.

    Args:
        email: user email.

    Returns:
        User: created user.
    """
    return User.objects.create_user(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


def _off_url(barcode: str) -> str:
    """Return the OFF API URL for a barcode.

    Args:
        barcode: product barcode.

    Returns:
        str: OFF API product URL.
    """
    return f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"


def _off_payload() -> dict:
    """Return a complete OFF payload.

    Returns:
        dict: OFF API payload.
    """
    return {
        "status": 1,
        "product": {
            "product_name": "Nutella",
            "brands": "Ferrero",
            "quantity": "350 g",
            "url": None,
            "nutriments": {
                "energy-kcal_100g": 539,
                "proteins_100g": 6.3,
                "fat_100g": 30.9,
                "carbohydrates_100g": 57.5,
                "saturated-fat_100g": None,
                "sugars_100g": None,
                "fiber_100g": None,
                "salt_100g": 0.107,
            },
        },
    }


def _lookup_query(selection: str) -> str:
    """Return a foodProductByBarcode query with the given selection.

    Args:
        selection: GraphQL selection set for the lookup field.

    Returns:
        str: GraphQL query.
    """
    return (
        f'{{ foodProductByBarcode(barcode: "{BARCODE}") '
        f"{{ {selection} }} }}"
    )


@pytest.mark.django_db
class TestFoodProductBarcodeLookup:
    """Tests for the food product barcode lookup query."""

    def _context(self, mocker, user):
        """Build a GraphQL context carrying the given user.

        Args:
            mocker: pytest-mock fixture.
            user: user to attach to the request.

        Returns:
            Mock: GraphQL context.
        """
        mock_context = mocker.Mock()
        mock_context.request.user = user
        return mock_context

    def test_lookup_returns_local_product_without_off_call(
        self, mocker, requests_mock
    ):
        """A local product wins and Open Food Facts is not queried."""
        user = _create_user("barcode-local@test.com")
        FoodProduct.objects.create(
            name="Local Oats",
            barcode=BARCODE,
            size=500,
            size_unit="g",
            num_servings=1,
            url="",
        )
        off = requests_mock.get(_off_url(BARCODE), json={"status": 0})

        result = schema.execute_sync(
            _lookup_query("product { id name } openFoodFacts { name }"),
            context_value=self._context(mocker, user),
        )

        assert result.errors is None
        lookup = result.data["foodProductByBarcode"]
        assert lookup["product"]["name"] == "Local Oats"
        assert lookup["openFoodFacts"] is None
        assert off.call_count == 0

    def test_lookup_returns_local_product_servings(
        self, mocker, requests_mock
    ):
        """A local product lookup can hydrate servings on demand."""
        user = _create_user("barcode-servings@test.com")
        product = FoodProduct.objects.create(
            name="Oats",
            barcode=BARCODE,
            size=500,
            size_unit="g",
            num_servings=1,
            url="",
        )
        Serving.objects.create(food=product, serving_size=50, serving_unit="g")
        off = requests_mock.get(_off_url(BARCODE), json={"status": 0})

        result = schema.execute_sync(
            _lookup_query(
                "product { id name servings { id servingSize "
                "servingUnit } } openFoodFacts { name }"
            ),
            context_value=self._context(mocker, user),
        )

        assert result.errors is None
        servings = result.data["foodProductByBarcode"]["product"]["servings"]
        assert any(
            serving["servingSize"] == 50.0 and serving["servingUnit"] == "g"
            for serving in servings
        )
        assert off.call_count == 0

    def test_lookup_returns_off_draft_when_not_local(
        self, mocker, requests_mock
    ):
        """An unknown local barcode returns the OFF product draft."""
        user = _create_user("barcode-off@test.com")
        requests_mock.get(_off_url(BARCODE), json=_off_payload())

        result = schema.execute_sync(
            _lookup_query(
                "product { id } openFoodFacts { "
                "barcode brand name url size sizeUnit numServings "
                "nutritionalInfoSize nutritionalInfoUnit "
                "energyKcal proteinG fatG carbsG saturatedFatG "
                "sugarsG fibreG saltG }"
            ),
            context_value=self._context(mocker, user),
        )

        assert result.errors is None
        lookup = result.data["foodProductByBarcode"]
        assert lookup["product"] is None
        draft = lookup["openFoodFacts"]
        assert draft["name"] == "Nutella"
        assert draft["brand"] == "Ferrero"
        assert draft["barcode"] == BARCODE
        assert draft["url"] == OFF_PRODUCT_PAGE
        assert draft["size"] == 350.0
        assert draft["sizeUnit"] == "g"
        assert draft["numServings"] == 1.0
        assert draft["nutritionalInfoSize"] == 100.0
        assert draft["nutritionalInfoUnit"] == "g"
        assert draft["energyKcal"] == 539.0
        assert draft["proteinG"] == 6.3
        assert draft["fatG"] == 30.9
        assert draft["carbsG"] == 57.5
        assert draft["saturatedFatG"] is None
        assert draft["sugarsG"] is None
        assert draft["fibreG"] is None
        assert draft["saltG"] == 0.11

    def test_lookup_unknown_barcode_returns_empty(self, mocker, requests_mock):
        """A barcode unknown to both sources returns an empty lookup."""
        user = _create_user("barcode-miss@test.com")
        requests_mock.get(_off_url(BARCODE), json={"status": 0})

        result = schema.execute_sync(
            _lookup_query("product { id } openFoodFacts { name }"),
            context_value=self._context(mocker, user),
        )

        assert result.errors is None
        assert result.data["foodProductByBarcode"] == {
            "product": None,
            "openFoodFacts": None,
        }

    def test_lookup_empty_barcode_skips_off(self, mocker, requests_mock):
        """A blank barcode returns an empty lookup without querying OFF."""
        user = _create_user("barcode-blank@test.com")
        off = requests_mock.get(
            _off_url(BARCODE), json={"status": 1, "product": {}}
        )

        result = schema.execute_sync(
            '{ foodProductByBarcode(barcode: "") '
            "{ product { id } openFoodFacts { name } } }",
            context_value=self._context(mocker, user),
        )

        assert result.errors is None
        assert result.data["foodProductByBarcode"] == {
            "product": None,
            "openFoodFacts": None,
        }
        assert off.call_count == 0

    def test_lookup_requires_authentication(self, mocker, requests_mock):
        """Anonymous users get an empty lookup without querying OFF."""
        off = requests_mock.get(
            _off_url(BARCODE), json={"status": 1, "product": {}}
        )
        mock_context = mocker.Mock()
        mock_context.request.user = AnonymousUser()

        result = schema.execute_sync(
            _lookup_query("product { id } openFoodFacts { name }"),
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["foodProductByBarcode"] == {
            "product": None,
            "openFoodFacts": None,
        }
        assert off.call_count == 0

    def test_lookup_without_request_user_returns_empty(
        self, mocker, requests_mock
    ):
        """A context without a request user gets an empty lookup."""
        off = requests_mock.get(
            _off_url(BARCODE), json={"status": 1, "product": {}}
        )
        mock_context = mocker.Mock()
        mock_context.request.user = None

        result = schema.execute_sync(
            _lookup_query("product { id } openFoodFacts { name }"),
            context_value=mock_context,
        )

        assert result.errors is None
        assert result.data["foodProductByBarcode"] == {
            "product": None,
            "openFoodFacts": None,
        }
        assert off.call_count == 0

    def test_lookup_off_failure_raises_graphql_error(
        self, mocker, requests_mock
    ):
        """OFF connectivity failures surface as GraphQL errors."""
        user = _create_user("barcode-error@test.com")
        requests_mock.get(
            _off_url(BARCODE),
            exc=requests.exceptions.ConnectionError,
        )

        result = schema.execute_sync(
            _lookup_query("product { id }"),
            context_value=self._context(mocker, user),
        )

        assert result.errors is not None
        assert "Open Food Facts lookup failed" in str(result.errors[0])
