"""Tests for the clone_preview_secrets script."""

import json
from subprocess import CompletedProcess

import pytest
from click.testing import CliRunner
from sanitise_branch import sanitise_branch_name
from clone_preview_secrets import main


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("clone_preview_secrets.subprocess.run")


def test_main_skip_main_branch(mock_run):
    """Test that secret cloning is skipped on the main branch."""
    runner = CliRunner()

    result = runner.invoke(main, ["main"])

    assert result.exit_code == 0
    assert "Branch is main. Skipping secret cloning." in result.output
    mock_run.assert_not_called()


def test_main_success(mock_run, mocker):
    """Test successful preview credential creation."""
    runner = CliRunner()
    mocker.patch("time.sleep")

    namespace_check = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    apply_ok = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    mock_run.side_effect = [namespace_check] + [apply_ok] * 5

    result = runner.invoke(main, ["feature/test-branch"])

    assert result.exit_code == 0
    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test-branch')}"
    assert f"Waiting for namespace {expected_ns} to exist..." in result.output
    assert (
        "Creating least-privilege preview secret nutrition-webapp-nextauth-secret..."
    ) in result.output
    assert (
        "Creating least-privilege preview secret nutrition-postgresql..."
    ) in result.output
    assert (
        "Creating least-privilege preview secret nutrition-gemini-api-key..."
    ) in result.output
    assert mock_run.call_count == 6

    # Secrets are created directly in the target namespace and never read from
    # staging.
    assert not any(
        call.args[0][:2] == ["kubectl", "get"]
        and call.args[0][3] == "-n"
        and call.args[0][4] == "nutrition-staging"
        for call in mock_run.call_args_list
    )


def test_main_apply_payload(mock_run, mocker):
    """Test that each generated secret contains expected preview keys."""
    runner = CliRunner()
    mocker.patch("time.sleep")

    namespace_check = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    apply_ok = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    mock_run.side_effect = [namespace_check] + [apply_ok] * 5

    runner.invoke(main, ["feature/test"])

    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"
    apply_calls = [
        call
        for call in mock_run.call_args_list
        if call.args[0][0:3] == ["kubectl", "apply", "-n"]
        and call.args[0][3] == expected_ns
    ]
    assert len(apply_calls) == 5

    for call in apply_calls:
        payload = json.loads(call.kwargs["input"].decode("utf-8"))
        assert payload["kind"] == "Secret"
        assert payload["type"] == "Opaque"
        assert payload["metadata"]["labels"]["app.kubernetes.io/managed-by"] == "nutrition-preview"
