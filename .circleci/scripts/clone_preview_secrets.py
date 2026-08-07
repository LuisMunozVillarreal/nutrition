"""Script to generate short-lived, least-privilege preview secrets in CI."""

import json
import secrets
import subprocess  # nosec: B404
import sys
import time

import click
from sanitise_branch import sanitise_branch_name

SECRET_SCHEMA = {
    "nutrition-webapp-nextauth-secret": {
        "nextauth-secret": lambda: secrets.token_urlsafe(32),
    },
    "nutrition-postgresql": {
        "postgresql-password": lambda: secrets.token_urlsafe(32),
    },
    "nutrition-django-secret-key": {
        "secret-key": lambda: secrets.token_urlsafe(64),
    },
    "nutrition-gemini-api-key": {
        "gemini-api-key": lambda: secrets.token_urlsafe(32),
    },
    "nutrition-gcp-db-backup-credentials": {
        "nutrition-gcp-db-backup-credentials.json": lambda: "{}",
    },
}
NAMESPACE_PREFIX = "nutrition-staging--"

TARGET_SECRET_PREFIX = "nutrition-preview"  # nosec: B105


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


def clone_secrets(target_namespace: str) -> None:
    """Create the required preview secrets directly in the target namespace.

    Args:
        target_namespace (str): The namespace to clone secrets to.
    """
    for secret_name, fields in SECRET_SCHEMA.items():
        exists = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", target_namespace],
            capture_output=True,
            check=False,
        )  # nosec: B603, B607
        if exists.returncode == 0:
            click.echo(f"Secret {secret_name} already exists. Skipping.")
            continue
        click.echo(f"Creating least-privilege preview secret {secret_name}...")
        try:
            secret_data = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": secret_name,
                    "namespace": target_namespace,
                    "labels": {
                        "app.kubernetes.io/managed-by": TARGET_SECRET_PREFIX,
                    },
                },
                "type": "Opaque",
                "stringData": {
                    key: generator() for key, generator in fields.items()
                },
            }

            subprocess.run(
                ["kubectl", "apply", "-n", target_namespace, "-f", "-"],
                input=json.dumps(secret_data).encode("utf-8"),
                check=True,
            )  # nosec: B603, B607
        except (OSError, subprocess.CalledProcessError) as e:
            click.echo(
                f"Error creating secret {secret_name}: {e}",
                err=True,
            )
            sys.exit(1)


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
    if not target_namespace.startswith(NAMESPACE_PREFIX):
        click.echo(
            f"ERROR: Invalid target namespace '{target_namespace}'.",
            err=True,
        )
        sys.exit(1)

    wait_for_namespace(target_namespace)
    clone_secrets(target_namespace)


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
