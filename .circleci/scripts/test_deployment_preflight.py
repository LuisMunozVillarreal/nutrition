"""Local, stdlib-only deployment preflight contracts; never contacts a cluster."""

import base64
import contextlib
import io
import json
import re
import subprocess  # nosec B404: Result and exception fixtures; run is mocked.
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import deployment_preflight as preflight

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = {
    "nutrition-gemini-api-key": ("gemini-api-key",),
    "nutrition-postgresql": ("postgresql-password",),
    "nutrition-django-secret-key": ("secret-key",),
    "nutrition-webapp-nextauth-secret": ("nextauth-secret",),
    "nutrition-gcp-db-backup-credentials": (
        "nutrition-gcp-db-backup-credentials.json",
    ),
    "nutrition-health-sync-secrets": ("token-pepper", "trusted-proxy-cidrs"),
}


class PreflightTests(unittest.TestCase):
    """Exercise preflight validation with captured, synthetic kubectl responses."""

    def setUp(self) -> None:
        """Initialize isolated fixtures and intercept every kubectl invocation."""
        self.target = "nutrition-production"
        # Any permits deliberately malformed JSON shapes in validation tests.
        self.resources: dict[str, Any] = {
            name: {
                "data": {key: self.encode("fixture-" + key) for key in keys}
            }
            for name, keys in CONTRACT.items()
        }
        self.set_health("trusted-proxy-cidrs", "198.51.100.0/24,2001:db8::/64")
        self.flux: Any = {"spec": {"suspend": False}}
        self.runner = patch.object(
            preflight.subprocess, "run", side_effect=self.fake_run
        )
        self.mock_run = self.runner.start()
        self.addCleanup(self.runner.stop)

    @staticmethod
    def encode(value: str) -> str:
        """Encode a synthetic secret value as Kubernetes secret data.

        Args:
            value: Plaintext fixture value.

        Returns:
            The base64-encoded UTF-8 value.
        """
        return base64.b64encode(value.encode()).decode()

    def set_health(self, key: str, value: str) -> None:
        """Replace one health-sync fixture key with an encoded value.

        Args:
            key: Health-sync secret key to replace.
            value: Plaintext fixture value.
        """
        self.resources["nutrition-health-sync-secrets"]["data"][key] = (
            self.encode(value)
        )

    def fake_run(
        self, command: list[str], **kwargs: bool | int
    ) -> subprocess.CompletedProcess[str]:
        """Check the read-only command contract and return a synthetic response.

        Args:
            command: Kubectl argument vector supplied by preflight.
            **kwargs: Capture flags and timeout supplied to subprocess.run.

        Returns:
            A completed process containing fixture JSON and a private error.
        """
        self.assertEqual(command[:2], ["kubectl", "get"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertGreater(kwargs["timeout"], 0)
        self.assertIn("--request-timeout=20s", command)
        namespace = command[command.index("-n") + 1]
        if command[2] == "kustomizations.kustomize.toolkit.fluxcd.io":
            self.assertEqual(namespace, "flux-system")
            payload = self.flux
        else:
            self.assertEqual(command[2], "secret")
            self.assertEqual(namespace, self.target)
            payload = self.resources.get(command[3])
        return subprocess.CompletedProcess(
            command,
            0 if payload is not None else 1,
            json.dumps(payload),
            "PRIVATE-RAW-ERROR",
        )

    def invoke(self, target: str = "nutrition-production") -> tuple[int, str]:
        """Invoke preflight and check that diagnostics omit resource values.

        Args:
            target: Matching main kustomization and namespace to check.

        Returns:
            The exit code and combined standard output and error text.
        """
        self.target = target
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            code = preflight.main(
                ["--kustomization", target, "--namespace", target]
            )
        self.assertNotIn("PRIVATE-RAW-ERROR", output.getvalue())
        self.assertNotIn("fixture-", output.getvalue())
        return code, output.getvalue()

    def test_valid_main_targets_only_read(self) -> None:
        """Accept both main targets using only the expected resource reads."""
        for target in ("nutrition-production", "nutrition-staging"):
            with self.subTest(target=target):
                self.mock_run.reset_mock()
                self.assertEqual(self.invoke(target)[0], 0)
                self.assertEqual(self.mock_run.call_count, 1 + len(CONTRACT))

    def test_absent_suspend_defaults_to_active(self) -> None:
        """Treat an absent suspend flag as active reconciliation."""
        self.flux = {"spec": {}}
        self.assertEqual(self.invoke()[0], 0)

    def test_suspended_stops_before_secrets_with_operator_instruction(
        self,
    ) -> None:
        """Stop at a suspended target and explain the operator resume action."""
        self.flux["spec"]["suspend"] = True
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("operator", output)
        self.assertIn("resume", output)
        self.assertIn(
            "flux resume kustomization nutrition-production -n flux-system",
            output,
        )
        self.assertEqual(self.mock_run.call_count, 1)

    def test_missing_each_secret(self) -> None:
        """Reject every missing required secret with its identifier."""
        for name in CONTRACT:
            with self.subTest(secret=name):
                saved = self.resources.pop(name)
                code, output = self.invoke()
                self.assertEqual(code, 1)
                self.assertIn(name, output)
                self.resources[name] = saved

    def test_missing_each_required_key(self) -> None:
        """Reject every missing required key with its identifier."""
        for name, keys in CONTRACT.items():
            for key in keys:
                with self.subTest(secret=name, key=key):
                    saved = self.resources[name]["data"].pop(key)
                    code, output = self.invoke()
                    self.assertEqual(code, 1)
                    self.assertIn(key, output)
                    self.resources[name]["data"][key] = saved

    def test_optional_fallbacks_not_required(self) -> None:
        """Accept fixtures that omit all optional rotation fallback keys."""
        self.assertEqual(self.invoke()[0], 0)

    def test_empty_pepper(self) -> None:
        """Reject empty and whitespace-only token peppers."""
        for value in ("", " \n\t"):
            with self.subTest(value=value):
                self.set_health("token-pepper", value)
                self.assertEqual(self.invoke()[0], 1)

    def test_pepper_independent_of_django_key(self) -> None:
        """Reject reuse of the Django secret key as the token pepper."""
        self.set_health("token-pepper", "fixture-secret-key")
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("independent", output)

    def test_secret_environment_references_are_rejected(self) -> None:
        """Reject indirection before Django can resolve different key values."""
        for name, key in (
            ("nutrition-health-sync-secrets", "token-pepper"),
            ("nutrition-django-secret-key", "secret-key"),
        ):
            for value in ("$SECRET_KEY", "$MISSING_SECRET", "${SECRET_KEY}"):
                with self.subTest(secret=name, value=value):
                    saved = self.resources[name]["data"][key]
                    self.resources[name]["data"][key] = self.encode(value)
                    code, output = self.invoke()
                    self.assertEqual(code, 1)
                    self.assertNotIn(value, output)
                    self.resources[name]["data"][key] = saved

    def test_invalid_cidrs(self) -> None:
        """Reject malformed, empty, host-only, and universal proxy networks."""
        for value in (
            "",
            " ",
            "PRIVATE-RAW-ERROR",
            "10.0.0.0/33",
            "0.0.0.0/0",
            "::/0",
            "10.42.0.0/16,::/0",
            "10.42.0.0/16,",
            "10.42.0.1",
            "198.51.100.1/24",
            " 127.0.0.1/32",
            "127.0.0.1/32 ",
            "127.0.0.1/32, ::1/128",
            "10.42.0.0/16,,fd00::/64",
        ):
            with self.subTest(value=value):
                self.set_health("trusted-proxy-cidrs", value)
                self.assertEqual(self.invoke()[0], 1)

    def test_invalid_secret_encoding_and_shapes(self) -> None:
        """Reject invalid secret encodings and malformed resource data."""
        value: object
        for value in ("PRIVATE-RAW-ERROR", "////", None, [], 7):
            with self.subTest(value=value):
                self.resources["nutrition-health-sync-secrets"]["data"][
                    "token-pepper"
                ] = value
                self.assertEqual(self.invoke()[0], 1)
        for value in ({}, {"data": None}, {"data": []}, []):
            with self.subTest(shape=value):
                self.resources["nutrition-health-sync-secrets"] = value
                self.assertEqual(self.invoke()[0], 1)

    def test_malformed_flux_fails_closed(self) -> None:
        """Reject Flux objects without a valid suspension state."""
        value: object
        for value in ([], {}, {"spec": None}, {"spec": {"suspend": "false"}}):
            with self.subTest(value=value):
                self.flux = value
                self.assertEqual(self.invoke()[0], 1)
                self.mock_run.reset_mock()

    def test_read_failures_are_sanitized(self) -> None:
        """Hide raw subprocess errors and invalid JSON from diagnostics."""
        for error in (
            OSError("PRIVATE-RAW-ERROR"),
            subprocess.TimeoutExpired("PRIVATE-RAW-ERROR", 30),
            subprocess.CalledProcessError(1, "PRIVATE-RAW-ERROR"),
        ):
            with self.subTest(error=type(error).__name__):
                self.mock_run.side_effect = error
                self.assertEqual(self.invoke()[0], 1)
        self.mock_run.side_effect = None
        for code, payload in (
            (1, "PRIVATE-RAW-ERROR"),
            (0, "PRIVATE-RAW-ERROR"),
        ):
            self.mock_run.return_value = subprocess.CompletedProcess(
                [], code, payload, "PRIVATE-RAW-ERROR"
            )
            self.assertEqual(self.invoke()[0], 1)


class ContractTests(unittest.TestCase):
    """Keep preflight assumptions aligned with repository manifests and CI."""

    def test_backend_preserves_conservative_proxy_trust(self) -> None:
        """Do not trust forwarded client entries from direct Service callers."""
        backend = (ROOT / "platform/k8s/base/backend.yaml").read_text()
        self.assertRegex(
            backend,
            r'name: HEALTH_SYNC_TRUSTED_PROXY_COUNT\s+value: "1"',
        )
        nginx = (
            ROOT
            / "backend/platform/docker/ansible/roles/nginx/templates"
            / "project_nginx.conf.j2"
        ).read_text()
        self.assertIn(
            "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            nginx,
        )
        self.assertIn("proxy_pass http://127.0.0.1:8000;", nginx)

    def test_explicit_contract_matches_required_manifest_references(
        self,
    ) -> None:
        """Match required secret references and mounted backup credentials."""
        expected: dict[str, set[str]] = {}
        for path in (ROOT / "platform/k8s").rglob("*.yaml"):
            source = path.read_text()
            for match in re.finditer(
                r"(?m)^( +)secretKeyRef:\n((?:\1  [^\n]*\n)+)", source
            ):
                fields = dict(
                    line.strip().split(": ", 1)
                    for line in match[2].splitlines()
                )
                if fields.get("optional") != "true":
                    expected.setdefault(fields["name"], set()).add(
                        fields["key"]
                    )
            # Mounted credential filename is consumed by the backend and backup job.
            for name in re.findall(
                r"secretName: (nutrition-gcp-db-backup-credentials)\b", source
            ):
                self.assertIn("/mnt/secret/" + name + ".json", source)
                expected.setdefault(name, set()).add(name + ".json")
        actual = {
            name: set(keys)
            for name, keys in preflight.REQUIRED_SECRET_KEYS.items()
        }
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual, {name: set(keys) for name, keys in CONTRACT.items()}
        )

    def test_ci_preflight_precedes_backend_patch_and_runs_tests(self) -> None:
        """Run contract tests in CI and preflight before patching the backend."""
        config = (ROOT / ".circleci/config.yml").read_text()
        rollout = config.split("  rollout-compatible-images:\n", 1)[1].split(
            "\n  validate:", 1
        )[0]
        self.assertLess(
            rollout.index("deployment_preflight.py"),
            rollout.index("name: Patch backend image first"),
        )
        self.assertIn(
            '--kustomization "<< parameters.kustomization_name >>"', rollout
        )
        self.assertIn(
            '--namespace "<< parameters.target_namespace >>"', rollout
        )
        job = config.split("  chart-contract-tests:\n", 1)[1].split(
            "\n  deploy-preview:", 1
        )[0]
        self.assertIn(
            "python3 -m unittest discover -s .circleci/scripts "
            "-p 'test_deployment_preflight.py'",
            job,
        )


if __name__ == "__main__":
    unittest.main()
