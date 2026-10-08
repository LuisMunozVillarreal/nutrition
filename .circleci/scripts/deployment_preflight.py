"""Read-only preflight for the staging and production main deployments.

The narrow key contract follows platform/k8s base workloads and main overlays.
The stdlib contract tests detect drift in required secretKeyRef entries and the
mounted backup credential filename. Optional rotation fallbacks are excluded.
"""

import argparse
import base64
import binascii
import ipaddress
import json
import subprocess
import sys

REQUIRED_SECRET_KEYS = {
    "nutrition-gemini-api-key": ("gemini-api-key",),
    "nutrition-postgresql": ("postgresql-password",),
    "nutrition-django-secret-key": ("secret-key",),
    "nutrition-webapp-nextauth-secret": ("nextauth-secret",),
    "nutrition-gcp-db-backup-credentials": (
        "nutrition-gcp-db-backup-credentials.json",
    ),
    "nutrition-health-sync-secrets": ("token-pepper", "trusted-proxy-cidrs"),
}
MAIN_TARGETS = ("nutrition-staging", "nutrition-production")


class PreflightError(Exception):
    """An operator-facing diagnostic containing no resource values."""


def read_resource(kind, name, namespace):
    """Capture all kubectl output; never propagate raw errors or JSON."""
    message = (
        f"Cannot read {kind}/{name}; check existence and read permissions."
    )
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                kind,
                name,
                "-n",
                namespace,
                "-o",
                "json",
                "--request-timeout=20s",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise PreflightError(message)
        resource = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise PreflightError(message) from None
    if not isinstance(resource, dict):
        raise PreflightError(message)
    return resource


def decode_key(data, name, key):
    """Decode only expected keys, reporting identifiers rather than values."""
    if key not in data:
        raise PreflightError(f"Secret {name} is missing required key {key}.")
    try:
        value = base64.b64decode(data[key], validate=True).decode("utf-8")
    except (ValueError, TypeError, binascii.Error):
        raise PreflightError(
            f"Secret {name} key {key} has invalid encoding."
        ) from None
    if not value.strip():
        raise PreflightError(f"Secret {name} key {key} must be nonempty.")
    return value


def check_preflight(kustomization, namespace):
    """Fail before rollout mutations; resuming reconciliation is operator-owned."""
    flux = read_resource(
        "kustomizations.kustomize.toolkit.fluxcd.io",
        kustomization,
        "flux-system",
    )
    spec = flux.get("spec")
    if not isinstance(spec, dict) or not isinstance(
        spec.get("suspend", False), bool
    ):
        raise PreflightError(
            "Cannot determine Flux Kustomization suspension state."
        )
    if spec.get("suspend", False):
        raise PreflightError(
            "Flux Kustomization is suspended. An operator must explicitly resume "
            "reconciliation when appropriate, then rerun deployment: "
            f"flux resume kustomization {kustomization} -n flux-system. "
            "Preflight never resumes automatically."
        )

    values = {}
    for name, keys in REQUIRED_SECRET_KEYS.items():
        secret = read_resource("secret", name, namespace)
        data = secret.get("data")
        if not isinstance(data, dict):
            raise PreflightError(
                f"Secret {name} has no valid required key data."
            )
        values[name] = {key: decode_key(data, name, key) for key in keys}

    health = values["nutrition-health-sync-secrets"]
    if (
        health["token-pepper"]
        == values["nutrition-django-secret-key"]["secret-key"]
    ):
        raise PreflightError(
            "Health-sync token-pepper must be independent of Django secret-key."
        )
    try:
        for entry in health["trusted-proxy-cidrs"].split(","):
            cidr = entry.strip()
            if "/" not in cidr or "%" in cidr:
                raise ValueError
            network = ipaddress.ip_network(cidr)
            if network.prefixlen == 0:
                raise ValueError
    except ValueError:
        raise PreflightError(
            "Health-sync trusted-proxy-cidrs must contain nonempty comma-separated "
            "IPv4/IPv6 CIDRs with narrow network prefixes; universal /0 is forbidden."
        ) from None


def main(argv=None):
    """Run preflight with fixed main targets and sanitized diagnostics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kustomization", required=True, choices=MAIN_TARGETS)
    parser.add_argument("--namespace", required=True, choices=MAIN_TARGETS)
    args = parser.parse_args(argv)
    if args.kustomization != args.namespace:
        print(
            "Deployment preflight failed: main target names must match.",
            file=sys.stderr,
        )
        return 1
    try:
        check_preflight(args.kustomization, args.namespace)
    except PreflightError as error:
        print(f"Deployment preflight failed: {error}", file=sys.stderr)
        return 1
    print("Deployment preflight passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
