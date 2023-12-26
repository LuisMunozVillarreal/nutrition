"""apps.goals.admin tests."""


def test_search_renders(logged_in_admin_client, fat_perc_goal, measurement):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/goals/fatpercgoal/?q=something"
    )

    # Then
    assert result.status_code == 200


def test_add_new_renders(logged_in_admin_client):
    """Admin add renders."""
    # When
    result = logged_in_admin_client.get("/admin/goals/fatpercgoal/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders(logged_in_admin_client, fat_perc_goal):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get("/admin/goals/fatpercgoal/1/change/")

    # Then
    assert result.status_code == 200
