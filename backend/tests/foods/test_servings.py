"""Tests for the serving model."""

from apps.foods.models.units import UNIT_CONTAINER


def test_serving_container_str(serving_factory):
    """Container serving includes size in the string representation."""
    # Given a serving with a container unit
    serving = serving_factory(
        serving_size=1,
        serving_unit=UNIT_CONTAINER,
    )

    # Then the string representation includes the size
    assert str(serving) == "Ocado Chicken Breast - 1 container (320g)"
