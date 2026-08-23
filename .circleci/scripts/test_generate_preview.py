"""Tests for the CircleCI flux preview generation script."""

import re
import subprocess

import pytest
from click.testing import CliRunner
from generate_flux_preview import _build_preview_rbac, generate_manifest, main
from sanitise_branch import MAX_LENGTH, sanitise_branch_name


@pytest.fixture
def mock_check_output(mocker):
    """Fixture to mock subprocess.check_output."""
    return mocker.patch("generate_flux_preview.subprocess.check_output")


@pytest.fixture
def mock_run(mocker):
    """Fixture to mock subprocess.run."""
    return mocker.patch("generate_flux_preview.subprocess.run")


def test_sanitize_branch():
    """Test branch sanitization is deterministic and collision-resistant."""
    branches = [
        "feature/new-ui",
        "feature/new/ui",
        "feature/new_ui",
        "JIRA_123",
        "feature/foo",
        "feature-foo",
        "feature+foo",
        "feature@foo",
        "",
        "___",
        "a" * 34,
        "a" * 35,
    ]

    for branch_input in branches:
        result = sanitise_branch_name(branch_input)
        assert result == sanitise_branch_name(branch_input)
        assert len(result) <= MAX_LENGTH
        assert result[0].isalnum() and result[-1].isalnum()
        assert (
            re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", result) is not None
        )


def test_sanitize_branch_is_case_resilient():
    """Test valid branch-case variants produce distinct outputs."""
    assert sanitise_branch_name("feature/Case-Branch") != sanitise_branch_name(
        "feature/case-branch"
    )


def test_sanitize_has_stable_hash_collision_resistance():
    """Regression test for collisions that normalize to the same slug."""
    slug_a = sanitise_branch_name("feature/foo")
    slug_b = sanitise_branch_name("feature-foo")
    slug_c = sanitise_branch_name("feature@foo")
    slug_d = sanitise_branch_name("feature+foo")

    assert slug_a != slug_b
    assert slug_a != slug_c
    assert slug_b != slug_c
    assert slug_c != slug_d


def test_sanitize_deterministic_collision_matrix():
    """Regression tests for deterministic output across collision-sensitive inputs."""
    candidate_branches = [
        "feature/foo",
        "feature-foo",
        "feature+foo",
        "feature@foo",
        "Feature/Foo",
        "feature/foo/",
        "_",
        "",
        "a" * 34,
        "a" * 35,
    ]

    sanitized = [sanitise_branch_name(branch) for branch in candidate_branches]
    assert len(sanitized) == len(set(sanitized))
    assert all(
        len(name) <= MAX_LENGTH
        and re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", name)
        for name in sanitized
    )


def test_build_preview_rbac_is_namespace_scoped():
    """Preview RBAC must be namespace-scoped and never cluster-scoped."""
    sanitized = sanitise_branch_name("feature/test")
    namespace = f"nutrition-staging--{sanitized}"
    rbac_manifest = _build_preview_rbac(namespace, sanitized)

    assert "kind: ClusterRole" not in rbac_manifest
    assert "kind: ClusterRoleBinding" not in rbac_manifest
    assert "namespace: flux-system" in rbac_manifest
    assert f"namespace: {namespace}" in rbac_manifest
    assert f"name: nutrition-preview-rbac-{sanitized}" in rbac_manifest
    assert f"name: nutrition-preview-sa-{sanitized}" in rbac_manifest
    assert f"name: nutrition-preview-sa-{sanitized}" in rbac_manifest


def test_generate_manifest_content():
    """Test manifest generation with custom domain."""
    branch = "feature/test"
    image_tag = "v1.0.0"
    preview_domain = "custom.example.com"

    manifest, sanitized = generate_manifest(branch, image_tag, preview_domain)

    assert sanitized == sanitise_branch_name(branch)
    assert f"name: nutrition-preview-{sanitized}" in manifest
    assert f"targetNamespace: nutrition-staging--{sanitized}" in manifest
    assert f"serviceAccountName: nutrition-preview-sa-{sanitized}" in manifest
    assert f"name: source-{sanitized}" in manifest
    assert "name: SKIP_DB_RESTORE" not in manifest
    assert "initContainers:" not in manifest
    assert 'value: "https://custom.example.com"' in manifest
    assert "newTag: v1.0.0" in manifest
    assert "value: custom.example.com" in manifest


def test_generate_manifest_default_domain():
    """Test manifest generation with default domain placeholder."""
    branch = "flux"
    image_tag = "latest"
    preview_domain = None

    manifest, _ = generate_manifest(branch, image_tag, preview_domain)

    sanitized = sanitise_branch_name(branch)
    assert f"staging--{sanitized}.${{BASE_DOMAIN}}" in manifest


def test_main_execution(mock_check_output, mock_run):
    """Test the main function with full execution."""
    mock_check_output.return_value = b"https://github.com/user/repo"
    runner = CliRunner()

    result = runner.invoke(main, ["feature/test", "v1"])

    sanitized = sanitise_branch_name("feature/test")

    assert result.exit_code == 0
    assert (
        "Applying Flux resources for branch 'feature/test' to cluster (preview"
        in result.output
    )
    assert (
        f"Successfully applied namespace, service account, "
        f"GitRepository 'source-{sanitized}' and Kustomization "
        f"'nutrition-preview-{sanitized}' as "
        f"'nutrition-preview-sa-{sanitized}'."
    ) in result.output
    mock_check_output.assert_called_with(
        ["git", "config", "--get", "remote.origin.url"]
    )
    mock_run.assert_called_once()


def test_main_dry_run(mock_check_output):
    """Test the main function dry-run mode."""
    mock_check_output.return_value = b"git@github.com:user/repo.git"
    runner = CliRunner()

    result = runner.invoke(main, ["feature/test", "v1", "--dry-run"])
    sanitized = sanitise_branch_name("feature/test")

    assert result.exit_code == 0
    assert (
        "--- Dry Run: Applying the following to cluster ---" in result.output
    )
    assert "url: ssh://git@github.com/user/repo.git" in result.output
    assert (
        f"serviceAccountName: nutrition-preview-sa-{sanitized}"
        in result.output
    )
    assert "SKIP_DB_RESTORE" not in result.output
    assert "kind: ServiceAccount" in result.output
    assert "kind: Role" in result.output
    assert "kind: RoleBinding" in result.output
    assert "branch: main" in result.output


def test_main_skip_main_branch():
    """Test that main branch is skipped."""
    runner = CliRunner()

    result = runner.invoke(main, ["main", "v1"])

    assert result.exit_code == 0
    assert (
        "Branch is main. Skipping preview generation (handled by prod flow)."
        in result.output
    )


def test_main_subprocess_error(mock_check_output, mock_run):
    """Test error handling during kubectl apply."""
    mock_check_output.return_value = b"https://github.com/user/repo"
    mock_run.side_effect = subprocess.CalledProcessError(1, "kubectl")
    runner = CliRunner()

    result = runner.invoke(main, ["feature/fail", "v1"])

    assert result.exit_code == 1
    assert "Failed to apply manifests" in result.output


def test_main_fallback_repo(mock_check_output):
    """Test fallback repo URL when git config fails."""
    mock_check_output.side_effect = subprocess.CalledProcessError(1, "git")
    runner = CliRunner()

    result = runner.invoke(main, ["feature/test", "v1", "--dry-run"])

    assert result.exit_code == 0
    assert (
        "url: https://github.com/LuisMunozVillarreal/nutrition"
        in result.output
    )
