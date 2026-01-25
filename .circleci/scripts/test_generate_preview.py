"""Tests for the CircleCI flux preview generation script."""

import subprocess

import pytest
from click.testing import CliRunner
from generate_flux_preview import generate_manifest, main
from sanitise_branch import sanitise_branch_name


@pytest.fixture
def mock_check_output(mocker):
    """Fixture to mock subprocess.check_output."""
    return mocker.patch("generate_flux_preview.subprocess.check_output")


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("generate_flux_preview.subprocess.run")


def test_sanitize_branch():
    """Test branch name sanitization logic."""
    # Given
    branches = [
        ("feature/new-ui", "feature-new-ui"),
        ("JIRA_123", "jira-123"),
        ("simple", "simple"),
        # Boundary condition: exactly 44 chars
        ("a" * 44, "a" * 44),
        # Over 44 chars: 45 chars -> truncated to 36 + hash
        (
            "a" * 45,
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-4642fe6",
        ),
        # Over 44 chars with hyphen at result cut
        (
            "feature/very/long/branch/name/that/exceeds/limit",
            "feature-very-long-branch-name-that-e-c8906af",
        ),
        (
            "dependabot/uv/backend/urllib3-2.6.3",
            "dependabot-uv-backend-urllib3-2-6-3",
        ),
    ]

    for branch_input, expected in branches:
        # When
        result = sanitise_branch_name(branch_input)

        # Then
        assert result == expected


def test_generate_manifest_content():
    """Test manifest generation with custom domain."""
    # Given
    branch = "feature/test"
    image_tag = "v1.0.0"
    preview_domain = "custom.domain.com"

    # When
    manifest, sanitized = generate_manifest(branch, image_tag, preview_domain)

    # Then
    assert sanitized == "feature-test"
    assert "name: nutrition-preview-feature-test" in manifest
    assert "targetNamespace: nutrition-staging--feature-test" in manifest
    assert "newTag: v1.0.0" in manifest
    assert "value: custom.domain.com" in manifest


def test_generate_manifest_default_domain():
    """Test manifest generation with default domain placeholder."""
    # Given
    branch = "flux"
    image_tag = "latest"
    preview_domain = None

    # When
    manifest, _ = generate_manifest(branch, image_tag, preview_domain)

    # Then
    assert "value: staging--flux.${BASE_DOMAIN}" in manifest


def test_main_execution(mock_check_output, mock_run):
    """Test the main function with full execution."""
    # Given
    mock_check_output.return_value = b"https://github.com/user/repo"
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/test", "v1"])

    # Then
    assert result.exit_code == 0
    assert "Applying Flux resources for branch 'feature/test'" in result.output
    # Verify git repo url logic
    mock_check_output.assert_called_with(
        ["git", "config", "--get", "remote.origin.url"]
    )
    mock_run.assert_called_once()


def test_main_dry_run(mock_check_output):
    """Test the main function dry-run mode."""
    # Given
    mock_check_output.return_value = b"git@github.com:user/repo.git"
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/test", "v1", "--dry-run"])

    # Then
    assert result.exit_code == 0
    assert (
        "--- Dry Run: Applying the following to cluster ---" in result.output
    )
    assert "url: ssh://git@github.com/user/repo.git" in result.output


def test_main_skip_main_branch():
    """Test that main branch is skipped."""
    # Given
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["main", "v1"])

    # Then
    assert result.exit_code == 0
    assert "Branch is main. Skipping preview generation" in result.output


def test_main_subprocess_error(mock_check_output, mock_run):
    """Test error handling during kubectl apply."""
    # Given
    mock_check_output.return_value = b"https://github.com/user/repo"
    mock_run.side_effect = subprocess.CalledProcessError(1, "kubectl")
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/fail", "v1"])

    # Then
    assert result.exit_code == 1
    assert "Failed to apply manifests" in result.output


def test_main_fallback_repo(mock_check_output):
    """Test fallback repo URL when git config fails."""
    # Given
    mock_check_output.side_effect = subprocess.CalledProcessError(1, "git")
    runner = CliRunner()

    # When
    result = runner.invoke(main, ["feature/test", "v1", "--dry-run"])

    # Then
    assert result.exit_code == 0
    assert (
        "url: https://github.com/LuisMunozVillarreal/nutrition"
        in result.output
    )
