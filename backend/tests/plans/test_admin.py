"""apps.plans.admin tests."""

import pytest


def test_search_renders_intake(logged_in_admin_client, intake):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/intake/?q=something")

    # Then
    assert result.status_code == 200


def test_search_renders_day(logged_in_admin_client, day):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/day/?q=something")

    # Then
    assert result.status_code == 200


def test_search_renders_weekplan(logged_in_admin_client, week_plan):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/weekplan/?q=something")

    # Then
    assert result.status_code == 200


@pytest.mark.parametrize("model", ["intake", "weekplan"])
def test_add_new_renders(logged_in_admin_client, model):
    """Admin add renders."""
    # When
    result = logged_in_admin_client.get(f"/admin/plans/{model}/add/")

    # Then
    assert result.status_code == 200


def test_edit_intake_renders(logged_in_admin_client, intake):
    """Admin edit day food renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/intake/1/change/")

    # Then
    assert result.status_code == 200


def test_edit_day_renders(logged_in_admin_client, day):
    """Admin edit day renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/day/1/change/")

    # Then
    assert result.status_code == 200


def test_edit_week_plan_renders(logged_in_admin_client, week_plan):
    """Admin edit week plan renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/weekplan/1/change/")

    # Then
    assert result.status_code == 200
