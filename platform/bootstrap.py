#!/usr/bin/env python3
"""Operator-only fresh installation; never called by deployment CI.

Keep all app parents and CI suspended throughout create and seed. SHA tags must
be approved, already-published commit images, never mutable aliases. This helper
does not establish image provenance or validate private runtime prerequisites.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

APPS = ("nutrition-production", "nutrition-staging")
RESOURCE = "kustomizations.kustomize.toolkit.fluxcd.io"
MARKER = "nutrition-bootstrap"


class BootstrapError(Exception):
    """A safe diagnostic that contains no private resource values."""


def kubectl(context, *args, body=None):
    """Capture API output and suppress raw diagnostics and endpoint addresses."""
    try:
        result = subprocess.run(
            ["kubectl", "--context", context, *args],
            input=body,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise BootstrapError(
            "kubectl failed; inspect privately before retrying."
        ) from None
    if result.returncode:
        raise BootstrapError(
            "kubectl failed; inspect privately before retrying."
        )
    return result.stdout


def read_apps(context):
    """Read both fixed targets; API errors must not be mistaken for absence."""
    return [
        json.loads(output) if output.strip() else None
        for name in APPS
        for output in [
            kubectl(
                context,
                "get",
                RESOURCE,
                name,
                "-n",
                "flux-system",
                "--ignore-not-found",
                "-o",
                "json",
                "--request-timeout=30s",
            )
        ]
    ]


def validate(resources, images=None, suspended=True):
    """Fail closed on existing migrations, wrong sources or unapproved images."""
    for name, resource in zip(APPS, resources):
        if not resource:
            raise BootstrapError("Both bootstrap children must exist.")
        meta, spec = resource["metadata"], resource["spec"]
        environment = name.removeprefix("nutrition-")
        if (
            meta["name"] != name
            or meta["namespace"] != "flux-system"
            or meta.get("annotations", {}).get(MARKER) != "suspended-images-v1"
            or spec.get("suspend") is not suspended
            or spec.get("sourceRef")
            != {"kind": "GitRepository", "name": "nutrition"}
            or spec.get("path") != f"./platform/k8s/overlays/{environment}"
            or spec.get("targetNamespace") != name
        ):
            raise BootstrapError(
                "Child is not in the expected fresh-install state."
            )
        if images is not None and spec.get("images") != images:
            raise BootstrapError(
                "Both approved image overrides must match before proceeding."
            )


def create(context):
    """Create only absent children, suspended from their very first API write."""
    if any(read_apps(context)):
        raise BootstrapError(
            "Children already exist; create never adopts an existing installation."
        )
    manifest = Path(__file__).parent / "flux/apps/applications.yaml"
    children = list(yaml.safe_load_all(manifest.read_text()))
    for child in children:
        child["metadata"].setdefault("annotations", {})[
            MARKER
        ] = "suspended-images-v1"
        child["spec"]["suspend"] = True
    validate(children)
    kubectl(
        context,
        "create",
        "-f",
        "-",
        "--request-timeout=30s",
        body=json.dumps(
            {"apiVersion": "v1", "kind": "List", "items": children}
        ),
    )
    validate(read_apps(context))


def change(context, action, images):
    """Seed while suspended or explicitly resume after checking both children."""
    resources = read_apps(context)
    validate(resources, images if action == "resume" else None)
    for resource in resources:
        assert resource is not None  # validate() rejects absent children.
        # Compare-and-swap guards prevent resuming or seeding changed resources.
        operations = [
            {
                "op": "test",
                "path": "/metadata/resourceVersion",
                "value": resource["metadata"]["resourceVersion"],
            },
            {"op": "test", "path": "/spec", "value": resource["spec"]},
            (
                {"op": "add", "path": "/spec/images", "value": images}
                if action == "seed"
                else {"op": "replace", "path": "/spec/suspend", "value": False}
            ),
        ]
        kubectl(
            context,
            "patch",
            RESOURCE,
            resource["metadata"]["name"],
            "-n",
            "flux-system",
            "--type=json",
            "-p",
            json.dumps(operations),
            "--request-timeout=30s",
        )
    validate(read_apps(context), images, suspended=action == "seed")


def main(argv=None):
    """Require explicit context, approved SHA tags and a separate resume action."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "seed", "resume"))
    parser.add_argument("--context", required=True)
    parser.add_argument("--backend-sha")
    parser.add_argument("--webapp-sha")
    args = parser.parse_args(argv)
    if not args.context.strip():
        parser.error("an explicit nonempty context is required")
    if args.action != "create" and not all(
        re.fullmatch(r"[0-9a-f]{40}", value or "")
        for value in (args.backend_sha, args.webapp_sha)
    ):
        parser.error(
            "seed and resume require two approved full lowercase commit SHA tags"
        )
    images = [
        {"name": f"luismunozvillarreal/nutrition-{component}", "newTag": sha}
        for component, sha in (
            ("backend", args.backend_sha),
            ("webapp", args.webapp_sha),
        )
    ]
    try:
        if args.action == "create":
            create(args.context)
        else:
            change(args.context, args.action, images)
    except (
        BootstrapError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        yaml.YAMLError,
    ):
        print(
            "Bootstrap stopped; inspect state privately. Do not resume unverified children.",
            file=sys.stderr,
        )
        return 1
    print(f"Bootstrap {args.action} verified for both children.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
