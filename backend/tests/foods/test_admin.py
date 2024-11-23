"""apps.foods.admin tests."""

#
# Cupboard
#


def test_search_renders_cupboard(logged_in_admin_client, cupboard_item):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/foods/cupboarditem/?q=something"
    )

    # Then
    assert result.status_code == 200


def test_add_new_renders_cupboard(logged_in_admin_client):
    """Admin new renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/cupboarditem/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders_cupboard(logged_in_admin_client, cupboard_item):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/cupboarditem/1/change/")

    # Then
    assert result.status_code == 200


#
# FoodProduct
#


def test_list_renders_food(logged_in_admin_client, food_product):
    """Admin list renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/foodproduct/")

    # Then
    assert result.status_code == 200


def test_search_renders_food(logged_in_admin_client, food_product):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/foods/foodproduct/?q=something"
    )

    # Then
    assert result.status_code == 200


def test_add_new_renders_food(logged_in_admin_client):
    """Admin new renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/foodproduct/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders_food(logged_in_admin_client, food_product):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/foodproduct/1/change/")

    # Then
    assert result.status_code == 200


#
# Recipe
#


def test_search_renders_recipe(logged_in_admin_client, recipe_ingredient):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/recipe/?q=something")

    # Then
    assert result.status_code == 200


def test_add_new_renders_recipe(logged_in_admin_client):
    """Admin new renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/recipe/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders_recipe(logged_in_admin_client, recipe_ingredient):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/recipe/1/change/")

    # Then
    assert result.status_code == 200
