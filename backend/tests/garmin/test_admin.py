"""Garmin admin immutability tests."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.garmin.models import GarminActivity, GarminConnection

User = get_user_model()


def _create_user(email: str, *, superuser: bool = False):
    create = (
        User.objects.create_superuser
        if superuser
        else User.objects.create_user
    )
    return create(
        email=email,
        password="password123",
        date_of_birth="2000-01-01",
        height=170.0,
    )


@pytest.mark.django_db
def test_connection_admin_permissions_are_strictly_view_only(rf):
    """Even superusers must not add, change, or delete connections."""
    superuser = _create_user(
        "garmin-admin-methods@example.com", superuser=True
    )
    owner = _create_user("garmin-admin-owner@example.com")
    connection = GarminConnection.objects.create(user=owner)
    request = rf.get("/admin/garmin/garminconnection/")
    request.user = superuser
    model_admin = admin.site._registry[GarminConnection]

    assert model_admin.has_view_permission(request, connection) is True
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request, connection) is False
    assert model_admin.has_delete_permission(request, connection) is False
    assert set(model_admin.get_readonly_fields(request, connection)) == set(
        model_admin.fields
    )
    assert "delete_selected" not in model_admin.get_actions(request)


@pytest.mark.django_db
def test_connection_admin_post_cannot_transfer_or_mutate_credentials(client):
    """A superuser POST must leave ownership, lifecycle, and secrets unchanged."""
    superuser = _create_user("garmin-admin-post@example.com", superuser=True)
    owner = _create_user("garmin-admin-post-owner@example.com")
    other = _create_user("garmin-admin-post-other@example.com")
    connection = GarminConnection.objects.create(
        user=owner,
        provider="garmin",
        provider_account_id="provider-owner",
        provider_scopes=["read"],
        status=GarminConnection.Status.ACTIVE,
        access_token_encrypted="encrypted-access",
        refresh_token_encrypted="encrypted-refresh",
    )
    original_access = connection.access_token_encrypted
    original_refresh = connection.refresh_token_encrypted
    original_generation = connection.connection_generation
    client.force_login(superuser)

    response = client.post(
        reverse("admin:garmin_garminconnection_change", args=[connection.pk]),
        {
            "user": other.pk,
            "provider": "other-provider",
            "provider_account_id": "other-account",
            "provider_scopes": '["write"]',
            "status": GarminConnection.Status.DISCONNECTED,
            "connection_generation": original_generation + 1,
        },
    )

    assert response.status_code == 403
    connection.refresh_from_db()
    assert connection.user_id == owner.pk
    assert connection.provider == "garmin"
    assert connection.provider_account_id == "provider-owner"
    assert connection.provider_scopes == ["read"]
    assert connection.status == GarminConnection.Status.ACTIVE
    assert connection.connection_generation == original_generation
    assert connection.access_token_encrypted == original_access
    assert connection.refresh_token_encrypted == original_refresh


@pytest.mark.django_db
def test_connection_admin_routes_expose_no_write_actions(client):
    """Add/delete routes and bulk delete stay unavailable to a superuser."""
    superuser = _create_user("garmin-admin-routes@example.com", superuser=True)
    owner = _create_user("garmin-admin-routes-owner@example.com")
    connection = GarminConnection.objects.create(user=owner)
    client.force_login(superuser)

    add_response = client.get(reverse("admin:garmin_garminconnection_add"))
    delete_response = client.get(
        reverse("admin:garmin_garminconnection_delete", args=[connection.pk])
    )
    changelist_response = client.get(
        reverse("admin:garmin_garminconnection_changelist")
    )

    assert add_response.status_code == 403
    assert delete_response.status_code == 403
    assert changelist_response.status_code == 200
    assert b"delete_selected" not in changelist_response.content
    assert b"action-select" not in changelist_response.content


@pytest.mark.django_db
def test_activity_admin_remains_strictly_immutable(rf):
    """Activity provenance must retain its existing view-only boundary."""
    superuser = _create_user(
        "garmin-activity-admin@example.com", superuser=True
    )
    request = rf.get("/admin/garmin/garminactivity/")
    request.user = superuser
    model_admin = admin.site._registry[GarminActivity]

    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request) is False
    assert model_admin.has_delete_permission(request) is False
    assert "delete_selected" not in model_admin.get_actions(request)
