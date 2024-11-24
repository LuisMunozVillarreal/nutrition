"""intake e2e tests."""

from decimal import Decimal

from apps.foods.models.units import UNIT_CONTAINER, UNIT_GRAM, UNIT_SERVING


def test_intake_e2e(
    db,
    food_product_factory,
    recipe_factory,
    recipe_ingredient_factory,
    day,
    intake_factory,
):
    """E2E intake test."""
    # pylint: disable=too-many-positional-arguments,too-many-arguments

    salmon = food_product_factory(
        brand="Ocado",
        name="Scottish Salmon Fillets Skin On",
        weight=240,
        weight_unit="g",
        num_servings=2,
        energy=236,
        protein_g=18.6,
        fat_g=17.8,
        carbs_g=0.4,
    )
    potatoes = food_product_factory(
        brand="Ocado",
        name="British Baby Potatoes",
        weight=1000,
        weight_unit="g",
        num_servings=2,
        energy=288,
        protein_g=1.8,
        fat_g=0.5,
        carbs_g=14.9,
    )
    mascarpone = food_product_factory(
        brand="Ocado",
        name="Italian Mascarpone",
        weight=250,
        weight_unit="g",
        num_servings=1,
        energy=404,
        protein_g=4.2,
        fat_g=41,
        carbs_g=3.8,
    )
    leeks = food_product_factory(
        brand="Ocado",
        name="Organic Leeks",
        weight=400,
        weight_unit="g",
        num_servings=1,
        energy=61,
        protein_g=1.5,
        fat_g=0.3,
        carbs_g=14.2,
    )
    dill = food_product_factory(
        brand="M&S",
        name="Dill",
        weight=25,
        weight_unit="g",
        num_servings=1,
        energy=43,
        protein_g=3.5,
        fat_g=1.1,
        carbs_g=7,
    )

    recipe = recipe_factory(
        name="Salmon en papillote con puerros a la crema",
        nutrients_from_ingredients=True,
        num_servings=Decimal(3),
        energy=0,
    )

    salmon = recipe_ingredient_factory(
        recipe=recipe,
        food=salmon.servings.get(unit=UNIT_CONTAINER),
        num_servings=Decimal("3"),
    )
    assert salmon.energy == Decimal("1699.2")
    potatoes = recipe_ingredient_factory(
        recipe=recipe,
        food=potatoes.servings.get(unit=UNIT_SERVING),
        num_servings=Decimal("1"),
    )
    assert potatoes.energy == Decimal("1440")
    mascarpone = recipe_ingredient_factory(
        recipe=recipe,
        food=mascarpone.servings.get(size=100),
        num_servings=Decimal("1.8"),
    )
    assert mascarpone.energy == Decimal("727.2")
    leeks = recipe_ingredient_factory(
        recipe=recipe,
        food=leeks.servings.get(size=100),
        num_servings=Decimal("4.5"),
    )
    assert leeks.energy == Decimal("274.5")
    dill = recipe_ingredient_factory(
        recipe=recipe,
        food=dill.servings.get(size=1, unit=UNIT_GRAM),
        num_servings=Decimal("10"),
    )
    assert dill.energy == Decimal("4.30")

    assert recipe.energy == Decimal("4145.200")

    serving = recipe.servings.first()

    assert serving.energy == Decimal("1381.73")

    intake = intake_factory(
        day=day,
        food=serving,
        num_servings=2,
    )

    assert intake.energy == Decimal("2763.46")
