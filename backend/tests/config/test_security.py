"""Tests for Django production security settings."""

import pytest
from django.core import checks
from django.test import override_settings


@pytest.mark.django_db
@override_settings(
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=86400,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
)
def test_admin_endpoints_enforce_secure_cookies_and_hsts(client):
    """Admin should expose secure-cookie and transport-security headers."""
    http_redirect = client.get(
        "/admin/login/",
        secure=False,
        follow=False,
    )
    assert http_redirect.status_code == 301
    assert http_redirect["Location"].startswith("https://")

    response = client.get(
        "/admin/login/",
        secure=True,
        follow=False,
    )
    assert response.status_code == 200
    assert "Strict-Transport-Security" in response.headers
    assert "max-age=86400" in response.headers["Strict-Transport-Security"]
    assert "includeSubDomains" in response.headers["Strict-Transport-Security"]
    assert "preload" in response.headers["Strict-Transport-Security"]
    assert response.cookies["csrftoken"]["secure"] is True


@pytest.mark.django_db
@override_settings(
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
    SECURE_HSTS_SECONDS=0,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=False,
    SECURE_HSTS_PRELOAD=False,
)
def test_admin_endpoints_allow_non_production_ssl_relaxed_mode(client):
    """Development-like toggles should not force HTTPS transport rules."""
    response = client.get(
        "/admin/login/",
        secure=False,
        follow=False,
    )
    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers
    assert not response.cookies["csrftoken"]["secure"]


@pytest.mark.django_db
@override_settings(
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=86400,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
    SECURE_REDIRECT_EXEMPT=[r"^healthz/$"],
)
def test_healthz_endpoint_bypasses_ssl_redirect(client):
    """Health checks stay reachable when HTTPS redirect is enabled."""
    response = client.get("/healthz/", secure=False)
    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
@override_settings(
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=86400,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
    ALLOWED_HOSTS=["example.com"],
    CSRF_TRUSTED_ORIGINS=["https://example.com"],
    DEBUG=False,
    SECRET_KEY="local-security-regression-key-with-plenty-of-entropy",
)
def test_deploy_check_is_clean_with_hardened_security_settings() -> None:
    """Deploy checks should not raise security warnings with hardened settings."""
    messages = checks.run_checks(include_deployment_checks=True)
    security_messages = [
        msg.id for msg in messages if msg.id and msg.id.startswith("security.")
    ]
    assert security_messages == []
