"""apps.plans.admin tests."""


import pytest


def test_search_renders_dayfood(logged_in_admin_client, day_food):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/dayfood/?q=something")

    # Then
    assert result.status_code == 200


def test_search_renders_daytracking(logged_in_admin_client, day_tracking):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/plans/daytracking/?q=something"
    )

    # Then
    assert result.status_code == 200


def test_search_renders_weekplan(logged_in_admin_client, week_plan):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/weekplan/?q=something")

    # Then
    assert result.status_code == 200


@pytest.mark.parametrize("model", ["dayfood", "daytracking", "weekplan"])
def test_add_new_renders(logged_in_admin_client, model):
    """Admin add renders."""
    # When
    result = logged_in_admin_client.get(f"/admin/plans/{model}/add/")

    # Then
    assert result.status_code == 200


def test_edit_day_food_renders(logged_in_admin_client, day_food):
    """Admin edit day food renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/dayfood/1/change/")

    # Then
    assert result.status_code == 200


def test_edit_day_tracking_renders(logged_in_admin_client, day_tracking):
    """Admin edit day tracking renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/daytracking/1/change/")

    # Then
    assert result.status_code == 200


def test_edit_week_plan_renders(logged_in_admin_client, week_plan):
    """Admin edit week plan renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/weekplan/1/change/")

    # Then
    assert result.status_code == 200
