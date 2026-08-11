"""Stable deployment ordering contract tests."""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parents[2] / ".circleci" / "config.yml"


def test_stable_deploys_roll_backend_before_nullable_webapp():
    """Stable environments keep the old webapp until the backend is ready."""
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    rollout = config["commands"]["rollout-compatible-images"]["steps"]

    first_patch = rollout[0]["run"]
    assert first_patch["name"] == "Patch backend image first"
    assert "CURRENT_WEBAPP_IMAGE=" in first_patch["command"]
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
