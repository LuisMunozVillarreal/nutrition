"""Script to clone Kubernetes secrets to preview namespaces in CI."""

import json
import subprocess  # nosec: B404
import sys
import time

import click
from sanitise_branch import sanitise_branch_name

REQUIRED_SECRETS = (
    "nutrition-webapp-nextauth-secret",
    "nutrition-postgresql",
    "nutrition-django-secret-key",
    "nutrition-gemini-api-key",
    "nutrition-gcp-db-backup-credentials",
)
OPTIONAL_SECRETS = (
    "nutrition-garmin-config",
)
SECRETS = REQUIRED_SECRETS + OPTIONAL_SECRETS
SOURCE_NS = "nutrition-staging"


def wait_for_namespace(namespace: str, timeout_seconds: int = 300) -> None:
    """Wait for the target namespace to exist in the cluster.

    Args:
        namespace (str): The target namespace to wait for.
        timeout_seconds (int): Maximum time to wait in seconds.
    """
    click.echo(f"Waiting for namespace {namespace} to exist...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        res = subprocess.run(
            ["kubectl", "get", "namespace", namespace],
            capture_output=True,
            check=False,
        )  # nosec: B603, B607
        if res.returncode == 0:
            click.echo(f"Namespace {namespace} exists.")
            return
        time.sleep(10)

    click.echo(
        f"ERROR: Namespace {namespace} did not appear after "
        f"{timeout_seconds} seconds.",
        err=True,
    )
    sys.exit(1)


def _clone_secret(
    secret: str, target_namespace: str, *, optional: bool
) -> None:
    """Clone one Secret while distinguishing absence from lookup errors.

    Args:
        secret: Source Secret object name.
        target_namespace: Namespace receiving the cloned Secret.
        optional: Whether a genuinely absent source Secret may be skipped.
    """
    click.echo(f"Copying {secret} from {SOURCE_NS} to {target_namespace}...")
    lookup = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            secret,
            "-n",
            SOURCE_NS,
            "--ignore-not-found=true",
            "-o",
            "json",
        ],
        capture_output=True,
        check=False,
    )  # nosec: B603, B607
    if lookup.returncode != 0:
        click.echo(f"Error looking up Secret {secret}.", err=True)
        sys.exit(1)
    if not lookup.stdout.strip():
        if optional:
            click.echo(f"Optional Secret {secret} is absent; skipping.")
            return
        click.echo(f"Required Secret {secret} is absent.", err=True)
        sys.exit(1)

    try:
        secret_data = json.loads(lookup.stdout)
    except json.JSONDecodeError:
        click.echo(f"Invalid response while reading Secret {secret}.", err=True)
        sys.exit(1)

    metadata = secret_data.get("metadata", {})
    for key in [
        "namespace",
        "resourceVersion",
        "uid",
        "creationTimestamp",
        "ownerReferences",
    ]:
        metadata.pop(key, None)

    apply_result = subprocess.run(
        ["kubectl", "apply", "-n", target_namespace, "-f", "-"],
        input=json.dumps(secret_data).encode("utf-8"),
        capture_output=True,
        check=False,
    )  # nosec: B603, B607
    if apply_result.returncode != 0:
        click.echo(f"Error applying Secret {secret}.", err=True)
        sys.exit(1)


def clone_secrets(target_namespace: str) -> None:
    """Clone the required secrets to the target namespace.

    Args:
        target_namespace (str): The namespace to clone secrets to.
    """
    for secret in REQUIRED_SECRETS:
        _clone_secret(secret, target_namespace, optional=False)
    for secret in OPTIONAL_SECRETS:
        _clone_secret(secret, target_namespace, optional=True)


@click.command()
@click.argument("branch")
def main(branch: str) -> None:
    """Clone secrets from staging to a preview namespace.

    Args:
        branch (str): The branch name to derive the preview namespace from.
    """
    if branch == "main":
        click.echo("Branch is main. Skipping secret cloning.")
        sys.exit(0)

    sanitized_branch = sanitise_branch_name(branch)
    target_namespace = f"nutrition-staging--{sanitized_branch}"

    wait_for_namespace(target_namespace)
    clone_secrets(target_namespace)


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
