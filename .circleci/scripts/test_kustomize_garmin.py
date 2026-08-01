"""Rendered Garmin Kustomize workload contracts."""

from __future__ import annotations

import shutil
import subprocess  # nosec: B404
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KUSTOMIZE_PATHS = {
    "base": "platform/k8s/base",
    "staging": "platform/k8s/overlays/staging",
    "production": "platform/k8s/overlays/production",
}
ACTIVE_GARMIN_URL_SETTINGS = {
    "GARMIN_AUTHORIZATION_URL",
    "GARMIN_TOKEN_URL",
    "GARMIN_ACTIVITIES_URL",
    "GARMIN_REVOKE_TOKEN_URL",
    "GARMIN_CALLBACK_URL",
    "GARMIN_PROVIDER_ORIGINS",
    "GARMIN_CALLBACK_ALLOWED_ORIGINS",
}


def _render(path: str) -> list[dict[str, Any]]:
    """Render one Kustomize path using the production CLI contract."""
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl is unavailable")
    result = subprocess.run(  # nosec: B603, B607
        ["kubectl", "kustomize", path],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [
        document
        for document in yaml.safe_load_all(result.stdout)
        if isinstance(document, dict)
    ]


def _workload(
    documents: list[dict[str, Any]], kind: str, name: str
) -> dict[str, Any]:
    """Find a named workload in rendered documents."""
    return next(
        document
        for document in documents
        if document.get("kind") == kind
        and document.get("metadata", {}).get("name") == name
    )


def _container(workload: dict[str, Any]) -> dict[str, Any]:
    """Return the application container from a supported workload."""
    spec = workload["spec"]
    if workload["kind"] == "CronJob":
        spec = spec["jobTemplate"]["spec"]["template"]["spec"]
    else:
        spec = spec["template"]["spec"]
    return spec["containers"][0]


def _environment(workload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index workload environment entries and reject duplicate names."""
    entries = _container(workload)["env"]
    indexed = {entry["name"]: entry for entry in entries}
    assert len(indexed) == len(entries)
    return indexed


def _is_complete_runtime_url(value: str) -> bool:
    """Return whether a URL is concrete, HTTPS, and not a repository placeholder."""
    if not value or any(marker in value for marker in ("${", "<", ">")):
        return False
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    placeholder_suffixes = (
        "example.com",
        ".example.com",
        ".invalid",
        ".localhost",
        ".test",
    )
    return (
        parsed.scheme == "https"
        and bool(hostname)
        and not any(
            hostname.endswith(suffix) for suffix in placeholder_suffixes
        )
        and parsed.username is None
        and parsed.password is None
    )


def _validate_scheduler_activation(documents: list[dict[str, Any]]) -> None:
    """Reject an active scheduler unless both workloads are fully configured."""
    backend = _workload(documents, "Deployment", "nutrition-backend")
    scheduler = _workload(documents, "CronJob", "nutrition-garmin-sync")
    if scheduler["spec"].get("suspend", False):
        return

    for workload in (backend, scheduler):
        environment = _environment(workload)
        assert environment["GARMIN_ENABLED"].get("value", "").lower() == "true"
        for name in ACTIVE_GARMIN_URL_SETTINGS:
            assert name in environment
            assert "value" in environment[name]
            values = environment[name]["value"].split(",")
            assert values and all(
                _is_complete_runtime_url(value.strip()) for value in values
            )
            if name.endswith("ORIGINS"):
                assert all(
                    urlparse(value.strip()).path in ("", "/")
                    for value in values
                )


def _synthetic_documents(
    *, suspended: bool, enabled: str
) -> list[dict[str, Any]]:
    """Build safe synthetic workloads for activation validation tests."""
    environment = [
        {"name": "GARMIN_ENABLED", "value": enabled},
        *[
            {
                "name": name,
                "value": (
                    f"https://{name.lower().replace('_', '-')}"
                    ".runtime.internal"
                    f"{'/' if name.endswith('ORIGINS') else '/path'}"
                ),
            }
            for name in ACTIVE_GARMIN_URL_SETTINGS
        ],
    ]
    pod = {"containers": [{"env": environment}]}
    return [
        {
            "kind": "Deployment",
            "metadata": {"name": "nutrition-backend"},
            "spec": {"template": {"spec": deepcopy(pod)}},
        },
        {
            "kind": "CronJob",
            "metadata": {"name": "nutrition-garmin-sync"},
            "spec": {
                "suspend": suspended,
                "jobTemplate": {"spec": {"template": {"spec": deepcopy(pod)}}},
            },
        },
    ]


@pytest.mark.parametrize("environment", KUSTOMIZE_PATHS)
def test_rendered_backend_and_scheduler_have_complete_garmin_parity(
    environment: str,
) -> None:
    """Every rendered backend and scheduler receives identical Garmin config."""
    documents = _render(KUSTOMIZE_PATHS[environment])
    backend = _workload(documents, "Deployment", "nutrition-backend")
    scheduler = _workload(documents, "CronJob", "nutrition-garmin-sync")
    backend_env = _environment(backend)
    scheduler_env = _environment(scheduler)
    backend_garmin = {
        name: value
        for name, value in backend_env.items()
        if name.startswith("GARMIN_")
    }
    scheduler_garmin = {
        name: value
        for name, value in scheduler_env.items()
        if name.startswith("GARMIN_")
    }

    assert scheduler_garmin == backend_garmin
    assert len(scheduler_garmin) == 24
    assert _container(scheduler)["image"] == _container(backend)["image"]
    assert {"POSTGRESQL_HOST", "POSTGRESQL_PASSWORD", "SECRET_KEY"} <= set(
        scheduler_env
    )
    for entry in scheduler_garmin.values():
        assert not ({"value", "valueFrom"} <= set(entry))
        reference = entry.get("valueFrom", {}).get("secretKeyRef")
        if reference and reference["name"] == "nutrition-garmin-config":
            assert reference["optional"] is True


@pytest.mark.parametrize(
    ("environment", "expected_suspended"),
    [("base", True), ("staging", True), ("production", True)],
)
def test_rendered_scheduler_is_suspended_by_default(
    environment: str, expected_suspended: bool
) -> None:
    """Every committed Kustomize environment keeps the scheduler suspended."""
    documents = _render(KUSTOMIZE_PATHS[environment])
    scheduler = _workload(documents, "CronJob", "nutrition-garmin-sync")

    assert scheduler["spec"]["suspend"] is expected_suspended
    _validate_scheduler_activation(documents)
    assert scheduler["spec"]["concurrencyPolicy"] == "Forbid"
    assert _container(scheduler)["command"] == [
        "python",
        "manage.py",
        "sync_garmin",
    ]


def test_active_scheduler_rejects_disabled_backend() -> None:
    """Activation requires Garmin enabled in both backend and scheduler."""
    documents = _synthetic_documents(suspended=False, enabled="true")
    backend = _workload(documents, "Deployment", "nutrition-backend")
    _environment(backend)["GARMIN_ENABLED"]["value"] = "false"

    with pytest.raises(AssertionError):
        _validate_scheduler_activation(documents)


def test_active_scheduler_rejects_disabled_scheduler() -> None:
    """Activation cannot rely on backend enablement alone."""
    documents = _synthetic_documents(suspended=False, enabled="true")
    scheduler = _workload(documents, "CronJob", "nutrition-garmin-sync")
    _environment(scheduler)["GARMIN_ENABLED"]["value"] = "false"

    with pytest.raises(AssertionError):
        _validate_scheduler_activation(documents)


@pytest.mark.parametrize("workload_kind", ["Deployment", "CronJob"])
@pytest.mark.parametrize(
    "placeholder", ["", "https://example.com/provider", "${URL}"]
)
def test_active_scheduler_rejects_incomplete_provider_configuration(
    workload_kind: str, placeholder: str
) -> None:
    """Activation rejects missing and repository-placeholder provider values."""
    documents = _synthetic_documents(suspended=False, enabled="true")
    name = (
        "nutrition-backend"
        if workload_kind == "Deployment"
        else "nutrition-garmin-sync"
    )
    workload = _workload(documents, workload_kind, name)
    _environment(workload)["GARMIN_TOKEN_URL"]["value"] = placeholder

    with pytest.raises(AssertionError):
        _validate_scheduler_activation(documents)


def test_active_scheduler_accepts_complete_synthetic_runtime_configuration() -> (
    None
):
    """Activation validation accepts explicit non-placeholder safe test values."""
    documents = _synthetic_documents(suspended=False, enabled="true")

    _validate_scheduler_activation(documents)
