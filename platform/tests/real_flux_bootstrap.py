#!/usr/bin/env python3
"""Opt-in integration regression. Writes only to an authorized disposable cluster.

Run beside a clean, local Nutrition fixture Git tree served to the disposable
cluster's flux-system/nutrition source on main. It appends empty overlays and a
parent, commits locally (never pushes), and deletes only its random test objects.
The real helper is imported unchanged; only APPS and its manifest location are
rebound to isolated fixtures. No subprocess/API/controller behavior is mocked.
"""

import argparse
import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "bootstrap.py"
MANAGER = "flux-client-side-apply"


def main():
    """Exercise create, seed, repeated parent adoption, resume and SSA repair."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--expected-cluster-uid", required=True)
    parser.add_argument("--kubectl", required=True, type=Path)
    parser.add_argument("--source-tree", required=True, type=Path)
    parser.add_argument(
        "--confirm-disposable", action="store_true", required=True
    )
    args = parser.parse_args()
    assert args.kubectl.is_absolute() and args.kubectl.name == "kubectl"
    os.environ["PATH"] = (
        str(args.kubectl.parent) + os.pathsep + os.environ["PATH"]
    )

    def command(argv, body=None):
        result = subprocess.run(
            argv,
            input=body,
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                "Command failed; inspect disposable state privately"
            )
        return result.stdout

    def kube(*argv, body=None):
        return command(
            [str(args.kubectl), "--context", args.context, *argv], body
        )

    def get(kind, name):
        return json.loads(
            kube(
                "-n",
                "flux-system",
                "get",
                kind,
                name,
                "-o",
                "json",
                "--show-managed-fields",
            )
        )

    cluster = json.loads(kube("get", "namespace", "kube-system", "-o", "json"))
    assert cluster["metadata"]["uid"] == args.expected_cluster_uid
    source = get("gitrepository", "nutrition")
    assert source["spec"]["ref"] == {"branch": "main"}
    # The source must be a local, credential-free disposable HTTP fixture.
    assert source["spec"]["url"].startswith("http://")
    assert "secretRef" not in source["spec"]
    repo = args.source_tree.resolve()
    assert (repo / ".git").exists()
    assert not command(
        ["git", "-C", str(repo), "status", "--porcelain"]
    ).strip()
    assert (
        command(["git", "-C", str(repo), "branch", "--show-current"]).strip()
        == "main"
    )

    def wait_for(predicate):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(2)
        raise AssertionError("Timed out waiting for real Flux reconciliation")

    def reconcile(kind, name):
        token = uuid.uuid4().hex
        kube(
            "-n",
            "flux-system",
            "annotate",
            kind,
            name,
            "reconcile.fluxcd.io/requestedAt=" + token,
            "--overwrite",
        )

        def done():
            obj = get(kind, name)
            status = obj.get("status", {})
            return (
                status.get("lastHandledReconcileAt") == token
                and status.get("observedGeneration")
                == obj["metadata"]["generation"]
                and any(
                    c["type"] == "Ready" and c["status"] == "True"
                    for c in status.get("conditions", [])
                )
            )

        wait_for(done)

    spec = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suffix = "bootstrap-test-" + uuid.uuid4().hex[:10]
    module.APPS = tuple(
        "nutrition-" + suffix + "-" + env for env in ("production", "staging")
    )
    parent_name = suffix
    fixture_path = Path("bootstrap-regression") / suffix
    template = list(
        yaml.safe_load_all(
            (SCRIPT.parent / "flux/apps/applications.yaml").read_text()
        )
    )
    children = []
    for original, name in zip(template, module.APPS):
        child = copy.deepcopy(original)
        child["metadata"]["name"] = name
        child["spec"]["targetNamespace"] = name
        overlay = Path("platform/k8s/overlays") / name.removeprefix(
            "nutrition-"
        )
        child["spec"]["path"] = "./" + str(overlay)
        child["spec"].pop("postBuild", None)
        (repo / overlay).mkdir(parents=True)
        (repo / overlay / "kustomization.yaml").write_text(
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\nresources: []\n"
        )
        children.append(child)
    (repo / fixture_path).mkdir(parents=True)
    (repo / fixture_path / "children.yaml").write_text(
        yaml.safe_dump_all(children)
    )
    (repo / fixture_path / "kustomization.yaml").write_text(
        "apiVersion: kustomize.config.k8s.io/v1beta1\n"
        "kind: Kustomization\nresources: [children.yaml]\n"
    )
    paths = [str(fixture_path)] + [c["spec"]["path"] for c in children]
    command(["git", "-C", str(repo), "add", "--", *paths])
    command(
        [
            "git",
            "-C",
            str(repo),
            "commit",
            "-m",
            "test: add harmless bootstrap ownership fixtures",
        ]
    )
    revision = command(["git", "-C", str(repo), "rev-parse", "HEAD"]).strip()
    reconcile("gitrepository", "nutrition")
    assert get("gitrepository", "nutrition")["status"]["artifact"][
        "revision"
    ].endswith(revision)
    parent = {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {"name": parent_name, "namespace": "flux-system"},
        "spec": {
            "interval": "10m",
            "path": "./" + str(fixture_path),
            "prune": False,
            "sourceRef": {"kind": "GitRepository", "name": "nutrition"},
        },
    }
    images = [
        {
            "name": "luismunozvillarreal/nutrition-" + component,
            "newTag": tag * 40,
        }
        for component, tag in (("backend", "a"), ("webapp", "b"))
    ]
    uids = {}

    def check(suspended):
        for name in module.APPS:
            obj = get("kustomization", name)
            assert obj["metadata"]["uid"] == uids[name], "Child was recreated"
            assert (
                obj["spec"].get("suspend") is suspended
            ), "Suspension lost during adoption"
            assert (
                obj["spec"].get("images") == images
            ), "Images lost during adoption"
            owned = set()
            for field in obj["metadata"].get("managedFields", []):
                if field["manager"] == MANAGER:
                    owned.update(field.get("fieldsV1", {}).get("f:spec", {}))
            # Prove ownership before rollout. After resume, also exercise the
            # child's controller and repeated parent applies, checking values.
            required = {"f:images", "f:suspend"} if suspended else set()
            assert (
                required <= owned
            ), "Retained ownership missing: " + json.dumps(
                [
                    {
                        "manager": f["manager"],
                        "operation": f["operation"],
                        "specKeys": sorted(
                            f.get("fieldsV1", {}).get("f:spec", {})
                        ),
                    }
                    for f in obj["metadata"].get("managedFields", [])
                ]
            )

    try:
        with tempfile.TemporaryDirectory(
            prefix="bootstrap-fixture-"
        ) as directory:
            manifest = Path(directory) / "flux/apps/applications.yaml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(yaml.safe_dump_all(children))
            module.__file__ = str(Path(directory) / "bootstrap.py")
            module.create(args.context)
            module.change(args.context, "seed", images)
            for name in module.APPS:
                obj = get("kustomization", name)
                uids[name] = obj["metadata"]["uid"]
                assert obj["spec"]["suspend"] is True
                assert obj["spec"]["images"] == images
            check(True)
            kube("create", "-f", "-", body=json.dumps(parent))
            reconcile("kustomization", parent_name)
            check(True)
            reconcile("kustomization", parent_name)
            check(True)
            print(
                "PASS: create/seed and repeated real parent adoption preserve images, suspension, UIDs and ownership"
            )
            module.change(args.context, "resume", images)
            reconcile("kustomization", parent_name)
            check(False)
            for name in module.APPS:
                reconcile("kustomization", name)
                assert (
                    not get("kustomization", name)
                    .get("status", {})
                    .get("inventory", {})
                    .get("entries", [])
                )
            reconcile("kustomization", parent_name)
            check(False)
            reconcile("kustomization", parent_name)
            check(False)
            print(
                "PASS: explicit resume and subsequent parent reconciliation retain both image pairs"
            )
            # Model the documented recovery case without touching app objects.
            kube(
                "-n",
                "flux-system",
                "patch",
                "kustomization",
                parent_name,
                "--type=merge",
                "-p",
                '{"spec":{"suspend":true}}',
            )
            for name in module.APPS:
                kube(
                    "-n",
                    "flux-system",
                    "patch",
                    "kustomization",
                    name,
                    "--field-manager=" + MANAGER,
                    "--type=merge",
                    "-p",
                    '{"spec":{"suspend":true}}',
                )
                kube(
                    "-n",
                    "flux-system",
                    "patch",
                    "kustomization",
                    name,
                    "--type=merge",
                    "-p",
                    '{"metadata":{"managedFields":[{}]}}',
                )
                assert not get("kustomization", name)["metadata"].get(
                    "managedFields"
                ), "Recovery fixture did not erase ownership"
                repair = {
                    "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
                    "kind": "Kustomization",
                    "metadata": {"name": name, "namespace": "flux-system"},
                    "spec": {"suspend": True, "images": images},
                }
                kube(
                    "apply",
                    "--server-side",
                    "--field-manager=" + MANAGER,
                    "-f",
                    "-",
                    body=json.dumps(repair),
                )
            check(True)
            kube(
                "-n",
                "flux-system",
                "patch",
                "kustomization",
                parent_name,
                "--type=merge",
                "-p",
                '{"spec":{"suspend":false}}',
            )
            reconcile("kustomization", parent_name)
            check(True)
            reconcile("kustomization", parent_name)
            check(True)
            print(
                "PASS: minimal SSA repair restores erased ownership and survives repeated adoption"
            )
    finally:
        # All overlays are empty and the parent has prune=false. Never delete app resources.
        kube(
            "-n",
            "flux-system",
            "delete",
            "kustomization",
            parent_name,
            "--ignore-not-found",
            "--wait=true",
            "--timeout=60s",
        )
        for name in module.APPS:
            kube(
                "-n",
                "flux-system",
                "delete",
                "kustomization",
                name,
                "--ignore-not-found",
                "--wait=true",
                "--timeout=60s",
            )
        print(
            "Cleaned up isolated test Kustomizations; local fixture Git commit retained"
        )


if __name__ == "__main__":
    main()
