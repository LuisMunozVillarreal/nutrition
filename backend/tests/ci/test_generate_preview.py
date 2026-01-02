"""Tests for the CircleCI flux preview generation script."""

import sys
import unittest
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


class TestGeneratePreview(unittest.TestCase):
    """Test suite for generate_flux_preview.py."""

    def test_sanitize_branch(self):
        """Test branch name sanitization logic."""
        self.assertEqual(
            sanitize_branch_name("feature/new-ui"), "feature-new-ui"
        )
        self.assertEqual(sanitize_branch_name("JIRA_123"), "jira-123")
        self.assertEqual(sanitize_branch_name("simple"), "simple")

    def test_generate_manifest_content(self):
        """Test manifest generation with custom domain."""
        manifest, sanitized = generate_manifest(
            "feature/test", "v1.0.0", "custom.domain.com"
        )
        self.assertEqual(sanitized, "feature-test")
        self.assertIn("name: nutrition-preview-feature-test", manifest)
        self.assertIn(
            "targetNamespace: nutrition-staging--feature-test", manifest
        )
        self.assertIn("newTag: v1.0.0", manifest)
        self.assertIn("value: custom.domain.com", manifest)  # Host override

    def test_generate_manifest_default_domain(self):
        """Test manifest generation with default domain placeholder."""
        manifest, sanitized = generate_manifest("flux", "latest", None)
        # Expecting the variable string literal in the output
        self.assertIn("value: staging--flux.${BASE_DOMAIN}", manifest)


if __name__ == "__main__":
    unittest.main()
