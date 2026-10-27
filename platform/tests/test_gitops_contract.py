"""Offline contracts for the app-only Flux installation."""

import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class GitOpsContracts(unittest.TestCase):
    """Cluster ownership must not leak back into the application repo."""

    def test_independent_source_and_ci_owned_images(self):
        """Render a complete standalone installation with stable CI targets."""
        entry = ROOT / "platform/flux"
        self.assertTrue(entry.is_dir(), "app-only Flux entry point is missing")
        output = subprocess.check_output(
            ["kubectl", "kustomize", str(entry)], text=True
        )
        documents = list(yaml.safe_load_all(output))
        sources = [d for d in documents if d["kind"] == "GitRepository"]
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source["metadata"]["name"], "nutrition")
        self.assertEqual(source["spec"]["secretRef"]["name"], "nutrition-git")
        self.assertEqual(source["spec"]["ref"], {"branch": "main"})
        self.assertTrue(source["spec"]["url"].endswith("/nutrition"))
        apps = [d for d in documents if d["kind"] == "Kustomization"]
        self.assertEqual(
            {d["metadata"]["name"] for d in apps},
            {"nutrition-production", "nutrition-staging"},
        )
        for app in apps:
            spec = app["spec"]
            self.assertEqual(spec["sourceRef"]["name"], "nutrition")
            self.assertNotIn("images", spec, "CI owns image tags")
            self.assertEqual(
                spec["postBuild"]["substituteFrom"][0]["name"],
                "cluster-settings",
            )
        self.assertEqual(
            {d["metadata"]["name"] for d in documents if d["kind"] == "Namespace"},
            {"nutrition-production", "nutrition-staging"},
        )

    def test_overlays_render_without_cluster_components(self):
        """Both overlays retain app storage and the ingress middleware."""
        for environment in ("production", "staging"):
            output = subprocess.check_output(
                ["kubectl", "kustomize", str(ROOT / "platform/k8s/overlays" / environment)],
                text=True,
            )
            documents = list(yaml.safe_load_all(output))
            kinds = {d["kind"] for d in documents}
            self.assertIn("PersistentVolumeClaim", kinds)
            self.assertIn("Middleware", kinds)
            self.assertFalse(kinds & {"HelmRelease", "HelmRepository", "CustomResourceDefinition"})


if __name__ == "__main__":
    unittest.main()
