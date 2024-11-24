"""apps.exercises.admin tests."""


def test_list_renders(logged_in_admin_client, exercise_factory):
    """Admin list renders."""
    # Given an exercise without distance
    exercise_factory(distance=None)

    # When the admin list is accessed
    result = logged_in_admin_client.get("/admin/exercises/exercise/")

    # Then the exercise is listed
    assert result.status_code == 200

    # And the distance is not shown
    # - This is seen in the coverage :)


def test_search_renders(logged_in_admin_client, exercise):
    """Admin search renders."""
    # When
    result = logged_in_admin_client.get(
        "/admin/exercises/exercise/?q=something"
    )

    # Then
    assert result.status_code == 200


def test_add_new_renders(logged_in_admin_client):
    """Admin add renders."""
    # When
    result = logged_in_admin_client.get("/admin/exercises/exercise/add/")

    # Then
    assert result.status_code == 200


def test_edit_renders(logged_in_admin_client, exercise):
    """Admin edit renders."""
    # When
    result = logged_in_admin_client.get("/admin/exercises/exercise/1/change/")

    # Then
    assert result.status_code == 200
