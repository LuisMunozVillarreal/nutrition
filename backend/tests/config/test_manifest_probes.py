"""Verify probe paths for manifest targets."""

import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def test_backend_probe_paths_in_checked_in_manifests() -> None:
    """Health probes in base and Helm deployment manifests use /healthz/."""
    k8s_deployment = PROJECT_ROOT / "platform/k8s/base/backend.yaml"
    helm_deployment = BACKEND_ROOT / "platform/kube/templates/deployment.yaml"

    assert "path: /healthz/" in k8s_deployment.read_text()
    assert k8s_deployment.read_text().count("path: /healthz/") >= 3
    assert "path: /admin/login/" not in k8s_deployment.read_text()
    assert "path: /healthz/" in helm_deployment.read_text()


@pytest.mark.skipif(
    shutil.which("kustomize") is None,
    reason="kustomize not installed in this environment",
)
def test_rendered_staging_and_production_overlays_use_healthz() -> None:
    """Rendered kustomize overlays for all backend environments use healthz."""
    for environment in ["staging", "production"]:
        output = subprocess.run(
            [
                "kustomize",
                "build",
                str(Path(f"platform/k8s/overlays/{environment}")),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        rendered = output.stdout
        assert "path: /healthz/" in rendered
        assert "path: /admin/login/" not in rendered
