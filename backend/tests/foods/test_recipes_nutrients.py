"""food recipes tests modules."""

# QuerySet internals and deferred imports are intentionally instrumented to
# verify pre-collector lock ordering without changing production behavior.
# pylint: disable=protected-access,import-outside-toplevel
# pylint: disable=too-many-arguments,too-many-positional-arguments

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.models.query import QuerySet

from apps.foods.models import Recipe, RecipeIngredient, Serving


def test_calculate_recipe_nutrients(db, recipe_ingredient):
    """Calculate recipe nutrients correctly."""
    # Given
    assert recipe_ingredient.food.protein_g == 25  # / 100 g
    assert recipe_ingredient.food.size == 100
    assert recipe_ingredient.protein_g == 25
    recipe = recipe_ingredient.recipe
    assert recipe.protein_g == 250

    # When
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # Then
    assert recipe.protein_g == 25
    assert recipe.servings.get().protein_g == Decimal("12.5")


def test_do_not_calculate_recipe_nutrients(db, recipe_ingredient):
    """Do not Calculate recipe nutrients when there is no change."""
    # Given
    recipe = recipe_ingredient.recipe
    assert recipe.protein_g == 250

    # When
    recipe.save()

    # Then
    assert recipe.protein_g == 250


def test_full_stale_recipe_save_preserves_concurrent_protected_state(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """An unrelated full save cannot restore stale mode, units, or totals."""
    recipe = recipe_factory(
        nutrients_from_ingredients=False,
        size=Decimal("500"),
        size_unit="g",
        nutritional_info_unit="g",
        protein_g=Decimal("99"),
    )
    product = food_product_factory(
        size=Decimal("1"), size_unit="kg", protein_g=Decimal("10")
    )
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("1"), serving_unit="kg"
    )
    recipe_ingredient_factory(recipe=recipe, food=serving)
    concurrent = Recipe.objects.get(pk=recipe.pk)
    stale = Recipe.objects.get(pk=recipe.pk)

    concurrent.nutrients_from_ingredients = True
    concurrent.size_unit = "kg"
    concurrent.nutritional_info_unit = "kg"
    concurrent.num_servings = Decimal("4")
    concurrent.save()
    stale.name = "Stale rename"
    stale.save()

    stale.refresh_from_db()
    assert stale.name == "Stale rename"
    assert stale.nutrients_from_ingredients is True
    assert stale.size_unit == "kg"
    assert stale.nutritional_info_unit == "kg"
    assert stale.num_servings == Decimal("4")
    assert stale.size == Decimal("1")
    assert stale.protein_g == Decimal("100")


def test_stale_recipe_save_can_explicitly_override_a_protected_field(
    db, recipe_factory
):
    """Listing a protected field in update_fields is an intentional write."""
    recipe = recipe_factory(nutrients_from_ingredients=False)
    concurrent = Recipe.objects.get(pk=recipe.pk)
    stale = Recipe.objects.get(pk=recipe.pk)
    concurrent.nutrients_from_ingredients = True
    concurrent.save(update_fields=["nutrients_from_ingredients"])

    stale.save(update_fields=["nutrients_from_ingredients"])

    stale.refresh_from_db()
    assert stale.nutrients_from_ingredients is False


def test_increase_recipe_nutrient(db, recipe_ingredient):
    """Increase recipe nutrient correctly."""
    # Given
    recipe = recipe_ingredient.recipe
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # When
    recipe_ingredient.num_servings = 2
    recipe_ingredient.save()

    # Then
    recipe.refresh_from_db()
    assert recipe.protein_g == 50


def test_decrease_recipe_nutrient(db, recipe_ingredient):
    """Decrease recipe nutrient correctly."""
    # Given
    recipe = recipe_ingredient.recipe
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # When
    recipe.ingredients.all().delete()

    # Then
    recipe.refresh_from_db()
    assert recipe.protein_g == 0


def test_do_not_decrease_recipe_nutrient(db, recipe_ingredient):
    """Do not decrease recipe nutrient correctly when there is no change."""
    # Given
    recipe = recipe_ingredient.recipe

    # When
    recipe.ingredients.all().delete()

    # Then
    recipe.refresh_from_db()
    assert recipe.protein_g == 250


def test_create_recipe_ingredient(db, recipe, recipe_ingredient_factory):
    """Create recipe ingredient correctly."""
    # Given
    recipe.nutrients_from_ingredients = True
    recipe.save()

    # When
    ingredient = recipe_ingredient_factory(recipe=recipe)

    # Then
    assert ingredient.protein_g == 25


def test_recipe_ingredient_quantity_scales_recipe_mass(
    db, recipe, recipe_ingredient_factory, serving
):
    """Ingredient mass includes fractional and multiple serving quantities."""
    recipe.nutrients_from_ingredients = True
    recipe.save()

    recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2.5")
    )

    recipe.refresh_from_db()
    assert recipe.size == Decimal("250")


def test_recipe_ingredient_keeps_coherent_serving_snapshot(
    db, recipe, recipe_ingredient_factory, serving
):
    """Serving edits cannot mix new mass with old ingredient nutrients."""
    ingredient = recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2")
    )
    original = (ingredient.size, ingredient.protein_g)

    serving.serving_size = Decimal("50")
    serving.save()
    ingredient.refresh_from_db()

    assert (ingredient.size, ingredient.protein_g) == original


def test_legacy_null_recipe_snapshot_is_lazily_resolved(
    db, recipe, recipe_ingredient_factory, serving
):
    """Ingredients written during expansion remain readable before backfill."""
    ingredient = recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2")
    )
    type(ingredient).objects.filter(pk=ingredient.pk).update(
        size_snapshot=None, size_snapshot_unit=None
    )
    ingredient.refresh_from_db()

    assert ingredient.size == Decimal("200")
    assert ingredient.effective_size_snapshot_unit == "g"


def test_saving_legacy_null_recipe_snapshot_dual_writes_it(
    db, recipe, recipe_ingredient_factory, serving
):
    """A new writer fills a nullable ingredient snapshot on any model save."""
    ingredient = recipe_ingredient_factory(
        recipe=recipe, food=serving, num_servings=Decimal("2")
    )
    type(ingredient).objects.filter(pk=ingredient.pk).update(
        size_snapshot=None, size_snapshot_unit=None
    )
    ingredient.refresh_from_db()

    ingredient.save(update_fields=["recipe"])

    ingredient.refresh_from_db()
    assert ingredient.size_snapshot == Decimal("200")
    assert ingredient.size_snapshot_unit == "g"


def test_recipe_aggregate_converts_mixed_mass_snapshot_units(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Recipe mass is converted instead of adding raw kilogram and gram values."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True,
        size=0,
        size_unit="g",
    )
    grams = food_product_factory(size=Decimal("100"), size_unit="g")
    kilograms = food_product_factory(size=Decimal("1"), size_unit="kg")
    gram_serving = Serving.objects.create(
        food=grams, serving_size=Decimal("250"), serving_unit="g"
    )
    kilogram_serving = Serving.objects.create(
        food=kilograms, serving_size=Decimal("1"), serving_unit="kg"
    )

    first = recipe_ingredient_factory(recipe=recipe, food=gram_serving)
    second = recipe_ingredient_factory(recipe=recipe, food=kilogram_serving)

    recipe.refresh_from_db()
    assert first.size_snapshot_unit == "g"
    assert second.size_snapshot_unit == "kg"
    assert recipe.size == Decimal("1250")


def test_recipe_ingredient_snapshot_survives_catalog_and_recipe_edits(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Unrelated saves never reinterpret a complete historical snapshot."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True,
        size=0,
        size_unit="g",
    )
    product = food_product_factory(
        size=Decimal("400"), size_unit="g", protein_g=Decimal("10")
    )
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("100"), serving_unit="g"
    )
    ingredient = recipe_ingredient_factory(recipe=recipe, food=serving)
    original = (
        ingredient.size_snapshot,
        ingredient.size_snapshot_unit,
        ingredient.protein_g,
    )

    serving.serving_size = Decimal("2")
    serving.serving_unit = "kg"
    serving.save()
    product.size = Decimal("3")
    product.size_unit = "kg"
    product.protein_g = Decimal("99")
    product.save()
    recipe.name = "Renamed"
    recipe.save(update_fields=["name"])
    ingredient.save(update_fields=["recipe"])

    ingredient.refresh_from_db()
    recipe.refresh_from_db()
    assert (
        ingredient.size_snapshot,
        ingredient.size_snapshot_unit,
        ingredient.protein_g,
    ) == original
    assert recipe.size == Decimal("100")


def test_recipe_aggregate_converts_mixed_volume_snapshot_units(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Compatible liquid snapshots are normalized to the recipe volume unit."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True,
        size=0,
        size_unit="ml",
        nutritional_info_unit="ml",
    )
    product = food_product_factory(
        size=Decimal("1"),
        size_unit="l",
        nutritional_info_unit="ml",
    )
    litre = Serving.objects.create(
        food=product, serving_size=Decimal("1"), serving_unit="l"
    )
    millilitres = Serving.objects.create(
        food=product, serving_size=Decimal("250"), serving_unit="ml"
    )

    recipe_ingredient_factory(recipe=recipe, food=litre)
    recipe_ingredient_factory(recipe=recipe, food=millilitres)

    recipe.refresh_from_db()
    assert recipe.size == Decimal("1250")


def test_recipe_ingredient_rejects_incompatible_snapshot_dimension(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """A mass recipe cannot persist a volume ingredient contribution."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True, size=0, size_unit="g"
    )
    product = food_product_factory(
        size=Decimal("1"),
        size_unit="l",
        nutritional_info_unit="ml",
    )
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("250"), serving_unit="ml"
    )

    with pytest.raises(ValidationError, match="incompatible"):
        recipe_ingredient_factory(recipe=recipe, food=serving)

    assert recipe.ingredients.count() == 0
    recipe.refresh_from_db()
    assert recipe.size == 0


@pytest.mark.parametrize("contextual_unit", ["container", "serving"])
def test_contextual_serving_snapshot_resolves_to_food_size_unit(
    db,
    contextual_unit,
    recipe_factory,
    food_product_factory,
    recipe_ingredient_factory,
):
    """Contextual serving labels are made concrete at ingredient write time."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True, size=0, size_unit="g"
    )
    product = food_product_factory(
        size=Decimal("600"), size_unit="g", num_servings=3
    )
    serving = product.servings.get(serving_unit=contextual_unit)

    ingredient = recipe_ingredient_factory(recipe=recipe, food=serving)

    recipe.refresh_from_db()
    assert ingredient.size_snapshot_unit == "g"
    assert recipe.size == (
        Decimal("600") if contextual_unit == "container" else Decimal("200")
    )


def test_recipe_size_unit_edit_reconverts_historical_snapshots(
    db, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Changing aggregate display unit preserves the ingredient's physical size."""
    recipe = recipe_factory(
        nutrients_from_ingredients=True, size=0, size_unit="g"
    )
    product = food_product_factory(size=Decimal("1"), size_unit="kg")
    serving = Serving.objects.create(
        food=product, serving_size=Decimal("1"), serving_unit="kg"
    )
    ingredient = recipe_ingredient_factory(recipe=recipe, food=serving)
    assert ingredient.size_snapshot == Decimal("1")

    recipe.size_unit = "kg"
    recipe.save(update_fields=["size_unit"])

    recipe.refresh_from_db()
    ingredient.refresh_from_db()
    assert recipe.size == Decimal("1")
    assert ingredient.size_snapshot == Decimal("1")
    assert ingredient.size_snapshot_unit == "kg"


def test_recipe_ingredient_create_locks_recipe_and_ingredients_before_write(
    db, mocker, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """A new contribution serializes on the recipe and existing ingredients."""
    recipe = recipe_factory(nutrients_from_ingredients=True, size=0)
    product = food_product_factory()
    serving = product.servings.first()
    recipe_lock = mocker.spy(type(recipe).objects, "select_for_update")
    ingredient_lock = mocker.spy(RecipeIngredient.objects, "select_for_update")

    recipe_ingredient_factory(recipe=recipe, food=serving)

    recipe_lock.assert_called()
    ingredient_lock.assert_called()


def test_recipe_joined_lock_queries_target_only_their_base_rows(
    db, mocker, recipe_factory, recipe_ingredient_factory
):
    """Recipe locks never add joined serving/food rows to the lock graph."""
    recipe = recipe_factory(nutrients_from_ingredients=True, size=0)
    recipe_ingredient_factory(recipe=recipe)
    lock_targets = []
    original_fetch_all = QuerySet._fetch_all

    def record_lock_targets(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if (
            was_unfetched
            and queryset.query.select_for_update
            and queryset.query.select_related
        ):
            lock_targets.append(
                (queryset.model, queryset.query.select_for_update_of)
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_lock_targets)
    recipe.name = "Joined lock audit"

    recipe.save()

    assert lock_targets == [(RecipeIngredient, ("self",))]


def test_bulk_serving_cascade_prelocks_all_affected_recipe_hierarchies(
    db, mocker, recipe_factory, food_product_factory, recipe_ingredient_factory
):
    """Serving cascades precompute every recipe before Collector signals run."""
    recipes = [
        recipe_factory(nutrients_from_ingredients=True, size=0)
        for _ in range(2)
    ]
    products = [food_product_factory() for _ in recipes]
    ingredients = [
        recipe_ingredient_factory(
            recipe=recipe,
            food=product.servings.get(serving_size=100, serving_unit="g"),
        )
        for recipe, product in zip(recipes, products, strict=True)
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (
                    queryset.model,
                    [row.pk for row in queryset._result_cache or ()],
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    Serving.objects.filter(
        pk__in=[ingredient.food_id for ingredient in ingredients]
    ).delete()

    assert locked_rows == [
        (Recipe, sorted(recipe.pk for recipe in recipes)),
        (
            RecipeIngredient,
            [
                ingredient.pk
                for ingredient in sorted(
                    ingredients, key=lambda row: (row.recipe_id, row.pk)
                )
            ],
        ),
    ]


@pytest.mark.parametrize(
    "delete_as",
    [
        "serving_instance",
        "serving_queryset",
        "food_instance",
        "food_product_queryset",
        "food_queryset",
    ],
)
def test_food_and_serving_deletion_paths_reuse_one_global_recipe_lock_bundle(
    db,
    mocker,
    recipe_factory,
    food_product_factory,
    recipe_ingredient_factory,
    delete_as,
):
    """Instance, queryset, and parent cascades lock each recipe hierarchy once."""
    recipes = [
        recipe_factory(nutrients_from_ingredients=True, size=0)
        for _ in range(2)
    ]
    product = food_product_factory()
    serving = product.servings.get(serving_size=100, serving_unit="g")
    ingredients = [
        recipe_ingredient_factory(recipe=recipe, food=serving)
        for recipe in reversed(recipes)
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (
                    queryset.model,
                    [row.pk for row in queryset._result_cache or ()],
                    queryset.db,
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    if delete_as == "serving_instance":
        serving.delete(using="default")
    elif delete_as == "serving_queryset":
        Serving.objects.using("default").filter(pk=serving.pk).delete()
    elif delete_as == "food_instance":
        product.delete(using="default")
    elif delete_as == "food_product_queryset":
        type(product).objects.using("default").filter(pk=product.pk).delete()
    else:
        from apps.foods.models import Food

        Food.objects.using("default").filter(pk=product.pk).delete()

    assert locked_rows == [
        (Recipe, sorted(recipe.pk for recipe in recipes), "default"),
        (
            RecipeIngredient,
            [
                ingredient.pk
                for ingredient in sorted(
                    ingredients, key=lambda row: (row.recipe_id, row.pk)
                )
            ],
            "default",
        ),
    ]
    assert not RecipeIngredient.objects.filter(
        pk__in=[ingredient.pk for ingredient in ingredients]
    ).exists()
    for recipe in recipes:
        recipe.refresh_from_db()
        assert recipe.size == Decimal("0.0")


def test_bulk_recipe_ingredient_delete_prelocks_all_rows_globally(
    db, mocker, recipe_factory, recipe_ingredient_factory
):
    """Collector order cannot invert locks across a multi-recipe deletion."""
    recipes = [
        recipe_factory(nutrients_from_ingredients=True, size=0)
        for _ in range(2)
    ]
    ingredients = [
        recipe_ingredient_factory(recipe=recipes[1]),
        recipe_ingredient_factory(recipe=recipes[0]),
    ]
    locked_rows = []
    original_fetch_all = QuerySet._fetch_all

    def record_locked_queryset(queryset):
        was_unfetched = queryset._result_cache is None
        original_fetch_all(queryset)
        if queryset.query.select_for_update and was_unfetched:
            locked_rows.append(
                (
                    queryset.model,
                    [row.pk for row in queryset._result_cache or ()],
                    queryset.db,
                )
            )

    mocker.patch.object(QuerySet, "_fetch_all", new=record_locked_queryset)

    RecipeIngredient.objects.using("default").filter(
        pk__in=[ingredient.pk for ingredient in ingredients]
    ).order_by("-pk").delete()

    assert locked_rows == [
        (Recipe, sorted(recipe.pk for recipe in recipes), "default"),
        (
            RecipeIngredient,
            [
                ingredient.pk
                for ingredient in sorted(
                    ingredients, key=lambda row: (row.recipe_id, row.pk)
                )
            ],
            "default",
        ),
    ]
