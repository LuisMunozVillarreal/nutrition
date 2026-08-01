"""Rendered Garmin Kustomize workload contracts."""

from __future__ import annotations

import shutil
import subprocess  # nosec: B404
from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
KUSTOMIZE_PATHS = {
    "base": "platform/k8s/base",
    "staging": "platform/k8s/overlays/staging",
    "production": "platform/k8s/overlays/production",
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
        name: value for name, value in backend_env.items() if name.startswith("GARMIN_")
    }
    scheduler_garmin = {
        name: value
        for name, value in scheduler_env.items()
        if name.startswith("GARMIN_")
    }

    assert scheduler_garmin == backend_garmin
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
    [("base", True), ("staging", True), ("production", False)],
)
def test_rendered_scheduler_activation_is_production_only(
    environment: str, expected_suspended: bool
) -> None:
    """Only the production overlay activates the non-overlapping scheduler."""
    documents = _render(KUSTOMIZE_PATHS[environment])
    scheduler = _workload(documents, "CronJob", "nutrition-garmin-sync")

    assert scheduler["spec"]["suspend"] is expected_suspended
    assert scheduler["spec"]["concurrencyPolicy"] == "Forbid"
    assert _container(scheduler)["command"] == [
        "python",
        "manage.py",
        "sync_garmin",
    ]
