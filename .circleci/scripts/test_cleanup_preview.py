"""Tests for the cleanup_flux_preview script."""

from subprocess import CompletedProcess

import pytest
from cleanup_flux_preview import main
from click.testing import CliRunner
from sanitise_branch import sanitise_branch_name


def _not_found_output() -> CompletedProcess:
    return CompletedProcess(
        args=["kubectl"], returncode=1, stdout="", stderr="not found"
    )


def _success_output() -> CompletedProcess:
    return CompletedProcess(
        args=["kubectl"], returncode=0, stdout="resource", stderr=""
    )


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("cleanup_flux_preview.subprocess.run")


def test_main_dry_run(mock_run):
    """Test the main function with dry-run enabled."""
    runner = CliRunner()

    result = runner.invoke(main, ["feature/test", "--dry-run"])
    sanitized = sanitise_branch_name("feature/test")

    assert result.exit_code == 0
    assert (
        "Cleaning up preview environment for branch 'feature/test'"
        in result.output
    )
    assert f"(sanitized: {sanitized})" in result.output
    assert "[Dry Run] kubectl delete kustomization" in result.output
    assert "[Dry Run] kubectl delete gitrepository" in result.output
    assert "[Dry Run] kubectl delete serviceaccount" in result.output
    assert "[Dry Run] kubectl delete namespace" in result.output
    mock_run.assert_not_called()


def test_main_execution_success(mock_run):
    """Test successful cleanup executes deletion and verifies resources are gone."""
    runner = CliRunner()
    # 4 delete calls then 4 get calls for verification
    mock_run.side_effect = [
        _success_output(),
        _success_output(),
        _success_output(),
        _success_output(),
        _not_found_output(),
        _not_found_output(),
        _not_found_output(),
        _not_found_output(),
    ]

    result = runner.invoke(main, ["feature/test"])

    assert result.exit_code == 0
    assert "Cleanup sequence completed." in result.output
    assert mock_run.call_count == 8


def test_main_partial_delete_failure(mock_run):
    """Test that cleanup exits non-zero when delete fails."""
    runner = CliRunner()
    failure = CompletedProcess(
        args=["kubectl"], returncode=1, stdout="", stderr="permission denied"
    )
    mock_run.side_effect = [_success_output(), failure]

    result = runner.invoke(main, ["feature/fail"])

    assert result.exit_code == 1
    assert "Failed to delete" in result.output
    assert "Cleanup sequence failed." in result.output


def test_main_retries_until_gone(mock_run, monkeypatch):
    """Test deletion verification retries transiently visible resources."""
    runner = CliRunner()
    # Delete calls
    outputs = [
        _success_output(),
        _success_output(),
        _success_output(),
        _success_output(),
    ]
    # Kustomization remains for 2 checks, then disappears
    outputs += [
        _success_output(),
        _success_output(),
        _not_found_output(),
    ]
    # Remaining resources are absent
    outputs += [_not_found_output(), _not_found_output(), _not_found_output()]

    mock_run.side_effect = outputs

    # Keep test execution fast even when waiting for transient existence.
    monkeypatch.setattr(
        "cleanup_flux_preview.time.sleep", lambda *_args, **_kwargs: None
    )
    result = runner.invoke(main, ["feature/test"])

    assert result.exit_code == 0
    assert "Waiting for kustomization" in result.output
    assert "Cleanup sequence completed." in result.output


def test_main_verification_failure(mock_run):
    """Test cleanup fails when resource verification cannot complete."""
    runner = CliRunner()
    mock_run.side_effect = [
        _success_output(),
        _success_output(),
        _success_output(),
        _success_output(),
        CompletedProcess(
            args=["kubectl"],
            returncode=1,
            stdout="",
            stderr="unable to check resource",
        ),
        _not_found_output(),
        _not_found_output(),
        _not_found_output(),
    ]

    result = runner.invoke(main, ["feature/test"])

    assert result.exit_code == 1
    assert "Unable to verify deletion of" in result.output
    assert "Cleanup sequence failed." in result.output


def test_main_already_absent_resources_succeed(mock_run):
    """Test cleanup succeeds when everything is already absent."""
    runner = CliRunner()
    mock_run.side_effect = [
        _success_output(),
        _success_output(),
        _success_output(),
        _success_output(),
        _not_found_output(),
        _not_found_output(),
        _not_found_output(),
        _not_found_output(),
    ]

    result = runner.invoke(main, ["feature/test"])

    assert result.exit_code == 0
    assert "Cleanup sequence completed." in result.output
    assert mock_run.call_count == 8


def test_main_delete_oserror_fails(mock_run):
    """Test cleanup fails when kubectl delete command raises a system error."""
    runner = CliRunner()
    mock_run.side_effect = [OSError("kaboom")]

    result = runner.invoke(main, ["feature/test"])

    assert result.exit_code == 1
    assert "Error deleting kustomization" in result.output
    assert "Cleanup sequence failed." in result.output


def test_main_skip_main_branch():
    """Test that the script skips cleanup for 'main' branch."""
    runner = CliRunner()
    result = runner.invoke(main, ["main"])

    assert result.exit_code == 0
    assert "Branch is main. Skipping cleanup." in result.output
