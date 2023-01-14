"""apps.measurements.admin tests."""


def test_search_renders(logged_in_admin_client, measurement):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/measurements/measurement/?q=something"
    )

    # Then
    assert result.status_code == 200


def test_add_new_renders(logged_in_admin_client):
    """Admin add renders."""
    # When
    result = logged_in_admin_client.get("/admin/measurements/measurement/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders(logged_in_admin_client, measurement):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/measurements/measurement/1/change/"
    )

    # Then
    assert result.status_code == 200
