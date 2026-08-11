"""Stable deployment ordering contract tests."""

import os
import subprocess
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parents[2] / ".circleci" / "config.yml"


def _run_first_patch(
    tmp_path: Path, lookup_mode: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the real first-patch shell block against a fake kubectl."""
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    command = config["commands"]["rollout-compatible-images"]["steps"][0][
        "run"
    ]["command"]
    command = command.replace(
        "<< parameters.target_namespace >>", "test-namespace"
    )
    command = command.replace(
        "<< parameters.kustomization_name >>", "test-release"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "kubectl.log"
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

if sys.argv[1] == "get":
    mode = os.environ["LOOKUP_MODE"]
    if mode == "existing":
        print("luismunozvillarreal/nutrition-webapp:old-tag", end="")
    elif mode == "forbidden":
        print("Error from server (Forbidden)", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0)

if sys.argv[1] == "patch":
    path = Path(os.environ["KUBECTL_LOG"])
    path.write_text(" ".join(sys.argv[1:]), encoding="utf-8")
    raise SystemExit(0)

raise SystemExit(2)
""",
        encoding="utf-8",
    )
    kubectl.chmod(0o755)

    environment = os.environ | {
        "CIRCLE_SHA1": "head-sha",
        "KUBECTL_LOG": str(log_path),
        "LOOKUP_MODE": lookup_mode,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return result, log


def test_stable_deploys_roll_backend_before_nullable_webapp():
    """Stable environments keep the old webapp until the backend is ready."""
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    rollout = config["commands"]["rollout-compatible-images"]["steps"]

    first_patch = rollout[0]["run"]
    assert first_patch["name"] == "Patch backend image first"
    assert "CURRENT_WEBAPP_IMAGE=" in first_patch["command"]
    assert "--ignore-not-found" in first_patch["command"]
    assert "|| true" not in first_patch["command"]
    first_patch_line = next(
        line
        for line in first_patch["command"].splitlines()
        if "kubectl patch kustomization" in line
    )
    assert first_patch_line.count("$CIRCLE_SHA1") == 1
    assert first_patch_line.count("$CURRENT_WEBAPP_TAG") == 1

    assert "wait-for-flux-reconciliation" in rollout[1]

    second_patch = rollout[2]["run"]
    assert second_patch["name"] == "Patch webapp image after backend"
    assert second_patch["command"].count("$CIRCLE_SHA1") == 2
    assert "wait-for-flux-reconciliation" in rollout[3]

    for job_name in ("deploy-staging", "deploy-production"):
        steps = config["jobs"][job_name]["steps"]
        assert any("rollout-compatible-images" in step for step in steps)
        assert not any(
            isinstance(step, dict)
            and step.get("run", {}).get("name")
            in {
                "Patch Staging Flux Kustomization",
                "Patch Production Flux Kustomization",
            }
            for step in steps
        )


def test_first_patch_retains_existing_webapp_tag(tmp_path: Path):
    """An established environment keeps its deployed webapp during phase one."""
    result, log = _run_first_patch(tmp_path, "existing")

    assert result.returncode == 0
    assert log.count("old-tag") == 1
    assert log.count("head-sha") == 1


def test_first_patch_handles_genuinely_absent_webapp(tmp_path: Path):
    """A fresh environment can safely deploy both images together."""
    result, log = _run_first_patch(tmp_path, "absent")

    assert result.returncode == 0
    assert log.count("head-sha") == 2


def test_first_patch_fails_closed_on_lookup_error(tmp_path: Path):
    """Lookup failures abort before patching instead of mimicking absence."""
    result, log = _run_first_patch(tmp_path, "forbidden")

    assert result.returncode != 0
    assert log == ""
