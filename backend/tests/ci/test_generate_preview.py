"""Tests for the CircleCI flux preview generation script."""

import sys
from pathlib import Path

# Add .circleci/scripts to path to allow importing from hidden directory
scripts_path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / ".circleci"
    / "scripts"
)
sys.path.append(str(scripts_path))

import generate_flux_preview  # noqa: F401, E402
from generate_flux_preview import (  # noqa: E402
    generate_manifest,
    sanitize_branch_name,
)


class TestGeneratePreview:
    """Test suite for generate_flux_preview.py."""

    def test_sanitize_branch(self):
        """Test branch name sanitization logic."""
        # Given
        branches = [
            ("feature/new-ui", "feature-new-ui"),
            ("JIRA_123", "jira-123"),
            ("simple", "simple"),
        ]

        for branch_input, expected in branches:
            # When
            result = sanitize_branch_name(branch_input)

            # Then
            assert result == expected

    def test_generate_manifest_content(self):
        """Test manifest generation with custom domain."""
        # Given
        branch = "feature/test"
        image_tag = "v1.0.0"
        preview_domain = "custom.domain.com"

        # When
        manifest, sanitized = generate_manifest(
            branch, image_tag, preview_domain
        )

        # Then
        assert sanitized == "feature-test"
        assert "name: nutrition-preview-feature-test" in manifest
        assert "targetNamespace: nutrition-staging--feature-test" in manifest
        assert "newTag: v1.0.0" in manifest
        assert "value: custom.domain.com" in manifest

    def test_generate_manifest_default_domain(self):
        """Test manifest generation with default domain placeholder."""
        # Given
        branch = "flux"
        image_tag = "latest"
        preview_domain = None

        # When
        manifest, sanitized = generate_manifest(
            branch, image_tag, preview_domain
        )

        # Then
        assert "value: staging--flux.${BASE_DOMAIN}" in manifest
