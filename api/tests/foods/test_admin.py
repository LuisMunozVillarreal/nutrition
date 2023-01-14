"""apps.foods.admin tests."""


#
# Food
#


def test_search_renders_food(logged_in_admin_client, food):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/food/?q=something")

    # Then
    assert result.status_code == 200


def test_add_new_renders_food(logged_in_admin_client):
    """Admin new renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/food/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders_food(logged_in_admin_client, food):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/food/1/change/")

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
    """Admin new renders."""
    # When
    result = logged_in_admin_client.get("/admin/foods/recipe/1/change/")

    # Then
    assert result.status_code == 200
