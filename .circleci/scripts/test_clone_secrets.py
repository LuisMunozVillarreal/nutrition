"""Tests for the clone_preview_secrets script."""

import json
from subprocess import CompletedProcess
from typing import Any

import pytest
from click.testing import CliRunner
from clone_preview_secrets import main
from sanitise_branch import sanitise_branch_name


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
    expected_ns = (
        f"nutrition-staging--{sanitise_branch_name('feature/test-branch')}"
    )
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
        assert (
            payload["metadata"]["labels"]["app.kubernetes.io/managed-by"]
            == "nutrition-preview"
        )


def test_main_does_not_read_staging_credentials(mock_run, mocker):
    """Test that preview secret creation does not read source staging secrets."""
    runner = CliRunner()
    mocker.patch("time.sleep")

    namespace_check = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    apply_ok = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    mock_run.side_effect = [namespace_check] + [apply_ok] * 5

    result = runner.invoke(main, ["feature/test"])
    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"

    assert result.exit_code == 0
    assert all(
        call.args[0] == ["kubectl", "get", "namespace", expected_ns]
        for call in mock_run.call_args_list
        if call.args[0][:2] == ["kubectl", "get"]
    )

    non_staging_read_attempts = [
        call.args[0]
        for call in mock_run.call_args_list
        if call.args[0][:2] == ["kubectl", "get"] and "-n" in call.args[0]
    ]
    assert not non_staging_read_attempts


def test_main_secrets_are_preview_scoped_and_non_empty(mock_run, mocker):
    """Test that each required preview secret uses generated values."""
    runner = CliRunner()
    mocker.patch("time.sleep")
    generated_tokens = [
        "token-1",
        "token-2",
        "token-3",
        "token-4",
    ]
    mocker.patch(
        "clone_preview_secrets.secrets.token_urlsafe",
        side_effect=lambda _n: generated_tokens.pop(0),
    )

    namespace_check = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    apply_ok = CompletedProcess(
        args=["kubectl"], returncode=0, stdout=b"", stderr=b""
    )
    mock_run.side_effect = [namespace_check] + [apply_ok] * 5

    result = runner.invoke(main, ["feature/test"])
    expected_ns = f"nutrition-staging--{sanitise_branch_name('feature/test')}"

    assert result.exit_code == 0
    apply_calls = [
        call
        for call in mock_run.call_args_list
        if call.args[0][0:3] == ["kubectl", "apply", "-n"]
        and call.args[0][3] == expected_ns
    ]
    assert len(apply_calls) == 5

    seen_values: list[str] = []
    for call in apply_calls:
        payload: dict[str, Any] = json.loads(
            call.kwargs["input"].decode("utf-8")
        )
        secrets_payload = payload["stringData"]
        assert secrets_payload
        seen_values.extend(secrets_payload.values())
    assert sorted(seen_values) == sorted(
        ["token-1", "token-2", "token-3", "token-4", "{}"]
    )
