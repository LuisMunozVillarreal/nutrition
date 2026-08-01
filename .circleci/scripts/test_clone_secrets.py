"""Tests for the clone_preview_secrets script."""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from clone_preview_secrets import SECRETS, main

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _secret_names(value):
    """Recursively collect Secret objects referenced by manifest data."""
    names = set()
    if isinstance(value, dict):
        reference = value.get("secretKeyRef")
        if isinstance(reference, dict) and reference.get("name"):
            names.add(reference["name"])
        secret = value.get("secret")
        if isinstance(secret, dict) and secret.get("secretName"):
            names.add(secret["secretName"])
        for nested in value.values():
            names.update(_secret_names(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(_secret_names(nested))
    return names


def test_preview_clones_every_base_workload_secret():
    """Preview Secret inventory must derive from every base workload ref."""
    required = set()
    for manifest_path in (REPOSITORY_ROOT / "platform/k8s/base").glob("*.yaml"):
        for document in yaml.safe_load_all(manifest_path.read_text()):
            required.update(_secret_names(document))

    assert required <= set(SECRETS)
    assert "nutrition-garmin-config" in required


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("clone_preview_secrets.subprocess.run")


def test_main_skip_main_branch(mock_run):
    """Test that secret cloning is skipped on the main branch."""
    # Given we have a CLI runner
    runner = CliRunner()

    # When we run the script for the 'main' branch
    result = runner.invoke(main, ["main"])

    # Then it should exit with code 0 and not run any subprocesses
    assert result.exit_code == 0
    assert "Branch is main. Skipping secret cloning." in result.output
    mock_run.assert_not_called()


def test_main_success(mock_run, mocker):
    """Test successful cloning of secrets."""
    # Given we have a CLI runner and our subprocess mocks succeed
    runner = CliRunner()
    mocker.patch("time.sleep")  # Avoid sleeping in tests

    # Mock responses for kubectl get namespace, secrets, and apply
    mock_get_ns = mocker.MagicMock()
    mock_get_ns.returncode = 0

    mock_get_secret = mocker.MagicMock()
    mock_get_secret.returncode = 0
    mock_get_secret.stdout = json.dumps(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "my-secret",
                "namespace": "nutrition-staging",
                "uid": "1234",
                "resourceVersion": "5678",
                "creationTimestamp": "2026-07-05T00:00:00Z",
            },
            "data": {"key": "value"},
        }
    ).encode("utf-8")

    mock_apply = mocker.MagicMock()
    mock_apply.returncode = 0

    mock_run.side_effect = [mock_get_ns] + [
        mock_get_secret,
        mock_apply,
    ] * len(SECRETS)

    # When we run the script for a preview branch
    result = runner.invoke(main, ["feature/test-branch"])

    # Then the script should succeed and wait for target namespace
    assert result.exit_code == 0
    msg_ns = (
        "Waiting for namespace "
        + "nutrition-staging--feature-test-branch to exist..."
    )
    assert msg_ns in result.output
    msg_exists = (
        "Namespace nutrition-staging--" + "feature-test-branch exists."
    )
    assert msg_exists in result.output
    assert "Copying nutrition-webapp-nextauth-secret" in result.output

    # And it should call kubectl get namespace once, plus get+apply per secret.
    assert mock_run.call_count == 1 + (len(SECRETS) * 2)

    # And it should remove unwanted metadata fields
    last_apply_call = mock_run.call_args_list[-1]
    applied_json = json.loads(last_apply_call[1]["input"].decode("utf-8"))
    assert "namespace" not in applied_json["metadata"]
    assert "uid" not in applied_json["metadata"]
    assert "resourceVersion" not in applied_json["metadata"]
    assert "creationTimestamp" not in applied_json["metadata"]
