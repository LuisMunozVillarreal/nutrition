"""Tests for the cleanup_flux_preview script."""

import pytest
from cleanup_flux_preview import main
from click.testing import CliRunner


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("cleanup_flux_preview.subprocess.run")


def test_main_dry_run(mock_run):
    """Test the main function with dry-run enabled."""
    # Given
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/test", "--dry-run"])

    # Then
    assert result.exit_code == 0
    assert (
        "Cleaning up preview environment for branch 'feature/test'"
        in result.output
    )
    assert "(sanitized: feature-test)" in result.output
    assert "[Dry Run] kubectl delete kustomization" in result.output
    assert "[Dry Run] kubectl delete gitrepository" in result.output
    assert "[Dry Run] kubectl delete namespace" in result.output
    mock_run.assert_not_called()


def test_main_execution(mock_run):
    """Test the main function execution (no dry-run)."""
    # Given
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/test"])

    # Then
    assert result.exit_code == 0
    assert "Executing: kubectl delete kustomization" in result.output
    assert "Cleanup sequence completed." in result.output
    assert mock_run.call_count == 3


def test_main_skip_main_branch(mock_run):
    """Test that the script skips cleanup for 'main' branch."""
    # Given
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["main"])

    # Then
    assert result.exit_code == 0
    assert "Branch is main. Skipping cleanup." in result.output
    mock_run.assert_not_called()


def test_main_subprocess_error(mock_run):
    """Test error handling during subprocess execution."""
    # Given
    mock_run.side_effect = OSError("Command failed")
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/fail"])

    # Then
    assert result.exit_code == 0
    assert "Error executing command: Command failed" in result.output
