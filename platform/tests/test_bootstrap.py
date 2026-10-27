"""Exercise the fresh-install bootstrap with a stateful, offline API double."""

import copy
import importlib.util
import io
import json
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "platform/bootstrap.py"


class BootstrapTests(unittest.TestCase):
    """No child may become active before both image overrides are verified."""

    def setUp(self):
        self.assertTrue(
            SCRIPT.exists(), "executable suspended bootstrap is missing"
        )
        spec = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.resources = {}
        self.events = []
        self.fail_verb = None
        self.drop_seed = False
        self.concurrent_change = False
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.enterContext(redirect_stderr(self.output))
        self.enterContext(
            patch.object(
                self.module.subprocess, "run", side_effect=self.kubectl
            )
        )

    def kubectl(self, command, **kwargs):
        """Model atomic JSON patches and creation; never invoke a real API."""
        args = command[3:]
        self.assertEqual(command[:3], ["kubectl", "--context", "test-context"])
        verb = args[0]
        if verb == self.fail_verb:
            return subprocess.CompletedProcess(
                command, 1, "", "private-error-sentinel"
            )
        if verb == "get":
            value = self.resources.get(args[2])
            self.events.append(("get", args[2]))
            output = json.dumps(value) if value else ""
        elif verb == "create":
            body = json.loads(kwargs["input"])
            for item in body["items"]:
                name = item["metadata"]["name"]
                self.assertNotIn(name, self.resources)
                self.assertIs(item["spec"]["suspend"], True)
                self.assertNotIn("images", item["spec"])
                item["metadata"]["resourceVersion"] = "1"
                self.resources[name] = item
                self.events.append(("create", name))
            output = ""
        elif verb == "patch":
            name = args[2]
            resource = copy.deepcopy(self.resources[name])
            if self.concurrent_change:
                resource["metadata"]["resourceVersion"] = "2"
            operations = json.loads(args[args.index("-p") + 1])
            for operation in operations:
                parts = operation["path"].strip("/").split("/")
                target = resource
                for part in parts[:-1]:
                    target = target[part]
                if operation["op"] == "test":
                    if target[parts[-1]] != operation["value"]:
                        return subprocess.CompletedProcess(
                            command, 1, "", "conflict"
                        )
                else:
                    target[parts[-1]] = operation["value"]
            self.events.append(
                ("patch", name, copy.deepcopy(resource["spec"]))
            )
            if not self.drop_seed:
                self.resources[name] = resource
            output = ""
        else:
            self.fail("unexpected kubectl command")
        return subprocess.CompletedProcess(command, 0, output, "")

    def run_action(self, action, backend="a" * 40, webapp="b" * 40):
        args = [action, "--context", "test-context"]
        if action != "create":
            args += ["--backend-sha", backend, "--webapp-sha", webapp]
        return self.module.main(args)

    def prepare(self):
        self.assertEqual(self.run_action("create"), 0)
        self.assertEqual(self.run_action("seed"), 0)

    def test_create_seed_verify_then_explicit_resume(self):
        self.prepare()
        self.assertTrue(
            all(r["spec"]["suspend"] for r in self.resources.values())
        )
        seeded_events = len(self.events)
        self.assertEqual(self.run_action("resume"), 0)
        self.assertEqual(len(self.resources), 2)
        for resource in self.resources.values():
            self.assertIs(resource["spec"]["suspend"], False)
            self.assertEqual(
                resource["spec"]["images"],
                [
                    {
                        "name": "luismunozvillarreal/nutrition-backend",
                        "newTag": "a" * 40,
                    },
                    {
                        "name": "luismunozvillarreal/nutrition-webapp",
                        "newTag": "b" * 40,
                    },
                ],
            )
        resume_events = self.events[seeded_events:]
        self.assertEqual(
            [event[0] for event in resume_events[:2]], ["get", "get"]
        )
        self.assertEqual(
            [
                event[0]
                for event in self.events[seeded_events - 2 : seeded_events]
            ],
            ["get", "get"],
        )
        for event in self.events:
            if event[0] == "patch" and event[2]["suspend"] is False:
                self.assertEqual(len(event[2]["images"]), 2)

    def test_normal_ci_preflight_requires_the_explicit_resume(self):
        # Exercise the actual CI gate, not a bootstrap-only suspension check.
        import base64

        spec = importlib.util.spec_from_file_location(
            "deployment_preflight",
            ROOT / ".circleci/scripts/deployment_preflight.py",
        )
        assert spec is not None and spec.loader is not None
        preflight = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preflight)

        def read_resource(kind, name, namespace):
            if kind == self.module.RESOURCE:
                return self.resources[name]
            self.assertIn(namespace, self.module.APPS)
            return {
                "data": {
                    key: base64.b64encode(
                        (
                            "198.51.100.0/24"
                            if key == "trusted-proxy-cidrs"
                            else "fixture-" + key
                        ).encode()
                    ).decode()
                    for key in preflight.REQUIRED_SECRET_KEYS[name]
                }
            }

        self.prepare()
        with patch.object(
            preflight, "read_resource", side_effect=read_resource
        ):
            for name in self.module.APPS:
                with self.assertRaises(preflight.PreflightError):
                    preflight.check_preflight(name, name)
            self.assertEqual(self.run_action("resume"), 0)
            for name in self.module.APPS:
                preflight.check_preflight(name, name)

    def test_create_never_adopts_existing_children(self):
        self.prepare()
        before = copy.deepcopy(self.resources)
        self.assertEqual(self.run_action("create"), 1)
        self.assertEqual(self.resources, before)

    def test_resume_checks_both_images_on_both_children_before_any_write(self):
        self.prepare()
        self.resources["nutrition-staging"]["spec"]["images"][1]["newTag"] = (
            "c" * 40
        )
        before = copy.deepcopy(self.resources)
        self.assertEqual(self.run_action("resume"), 1)
        self.assertEqual(self.resources, before)

    def test_resume_without_seed_fails_closed(self):
        self.assertEqual(self.run_action("create"), 0)
        self.assertEqual(self.run_action("resume"), 1)
        self.assertTrue(
            all(r["spec"]["suspend"] for r in self.resources.values())
        )

    def test_seed_rejects_active_child_before_any_write(self):
        self.prepare()
        self.resources["nutrition-staging"]["spec"]["suspend"] = False
        before = copy.deepcopy(self.resources)
        self.assertEqual(self.run_action("seed"), 1)
        self.assertEqual(self.resources, before)

    def test_migration_children_are_not_bootstrap_targets(self):
        self.prepare()
        del self.resources["nutrition-staging"]["metadata"]["annotations"]
        before = copy.deepcopy(self.resources)
        self.assertEqual(self.run_action("seed"), 1)
        self.assertEqual(self.resources, before)

    def test_mutable_or_short_tags_rejected_without_api_calls(self):
        for tag in ("latest", "main", "abc123", "A" * 40, "a" * 39, "a" * 41):
            for component in ("backend", "webapp"):
                with self.subTest(tag=tag, component=component):
                    with self.assertRaises(SystemExit) as error:
                        self.run_action("seed", **{component: tag})
                    self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.events, [])

    def test_empty_context_rejected_without_api_calls(self):
        with self.assertRaises(SystemExit) as error:
            self.module.main(["create", "--context", ""])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.events, [])

    def test_api_failure_does_not_create_or_leak_raw_errors(self):
        self.fail_verb = "get"
        self.assertEqual(self.run_action("create"), 1)
        self.assertEqual(self.resources, {})
        self.assertNotIn("private-error-sentinel", self.output.getvalue())

    def test_seed_readback_detects_failed_persistence(self):
        self.assertEqual(self.run_action("create"), 0)
        self.drop_seed = True
        self.assertEqual(self.run_action("seed"), 1)
        self.assertEqual(self.run_action("resume"), 1)
        self.assertTrue(
            all(r["spec"]["suspend"] for r in self.resources.values())
        )

    def test_concurrent_change_prevents_resume(self):
        self.prepare()
        self.concurrent_change = True
        self.assertEqual(self.run_action("resume"), 1)
        self.assertTrue(
            all(r["spec"]["suspend"] for r in self.resources.values())
        )


if __name__ == "__main__":
    unittest.main()
