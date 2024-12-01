"""apps.plans.admin tests."""

import datetime

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


@pytest.fixture
def time(mocker, request):
    """Time mock."""
    mock = mocker.patch("apps.plans.admin.intake.datetime", wraps=datetime)
    time_mock = mocker.MagicMock()
    time_mock.time.return_value = datetime.time(*request.param)
    mock.datetime.now.return_value = time_mock
    return mock


@pytest.mark.parametrize(
    "time", [(9, 0), (13, 0), (16, 0), (21, 0)], indirect=True
)
def test_add_new_intake_renders(logged_in_admin_client, time):
    """Admin add intake renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/intake/add/")

    # Then
    assert result.status_code == 200


@pytest.fixture
def today(mocker):
    """Today mock."""
    mock = mocker.patch("apps.plans.admin.intake.datetime", wraps=datetime)
    mock.date.today.return_value = datetime.date(2023, 1, 9)
    return mock


def test_add_new_intake_with_existing_day(logged_in_admin_client, today, day):
    """Admin add intake with existing day."""
    # When
    result = logged_in_admin_client.get("/admin/plans/intake/add/")

    # Then
    assert result.status_code == 200


def test_add_new_weekplan_renders(logged_in_admin_client):
    """Admin add weekplan renders."""
    # When
    result = logged_in_admin_client.get("/admin/plans/weekplan/add/")

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
