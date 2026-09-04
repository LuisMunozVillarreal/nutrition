"""Script to generate short-lived, least-privilege preview secrets in CI."""

import json
import secrets
import subprocess  # nosec: B404
import sys
import time

import click
from sanitise_branch import sanitise_branch_name

GENERATED_SECRET_SCHEMA = {
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
    "nutrition-health-sync-secrets": {
        "token-pepper": lambda: secrets.token_urlsafe(64),
        "trusted-proxy-cidrs": lambda: "10.0.0.0/8",
    },
}

# The db-restore init container pulls a production database snapshot into every
# preview, so it needs the real GCP backup credentials. Unlike the other preview
# secrets (which are generated fresh, least-privilege values), this one must be
# copied from staging or the restore cannot authenticate.
COPIED_SECRETS = ["nutrition-gcp-db-backup-credentials"]
SOURCE_NAMESPACE = "nutrition-staging"

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


def _secret_exists(secret_name: str, namespace: str) -> bool:
    """Return True when the secret already exists in the namespace."""
    res = subprocess.run(
        ["kubectl", "get", "secret", secret_name, "-n", namespace],
        capture_output=True,
        check=False,
    )  # nosec: B603, B607
    return res.returncode == 0


def _deployment_exists(deployment_name: str, namespace: str) -> bool:
    """Return True when a deployment already exists in the namespace."""
    res = subprocess.run(
        ["kubectl", "get", "deployment", deployment_name, "-n", namespace],
        capture_output=True,
        check=False,
    )  # nosec: B603, B607
    return res.returncode == 0


def _create_generated_secret(
    secret_name: str,
    fields: dict,
    target_namespace: str,
) -> None:
    """Apply a freshly generated secret into the target namespace."""
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
        "stringData": {key: generator() for key, generator in fields.items()},
    }

    subprocess.run(
        ["kubectl", "apply", "-n", target_namespace, "-f", "-"],
        input=json.dumps(secret_data).encode("utf-8"),
        check=True,
    )  # nosec: B603, B607


def _copy_secret_from_source(secret_name: str, target_namespace: str) -> None:
    """Copy an existing secret's payload from the source namespace.

    The copy keeps only the secret's data payload and re-labels it as preview
    managed, discarding source metadata such as resourceVersion, owner
    references, and last-applied annotations.
    """
    res = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            secret_name,
            "-n",
            SOURCE_NAMESPACE,
            "-o",
            "json",
        ],
        capture_output=True,
        check=True,
    )  # nosec: B603, B607
    source = json.loads(res.stdout)

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
        "type": source.get("type", "Opaque"),
        "data": source.get("data", {}),
    }

    subprocess.run(
        ["kubectl", "apply", "-n", target_namespace, "-f", "-"],
        input=json.dumps(secret_data).encode("utf-8"),
        check=True,
    )  # nosec: B603, B607


def clone_secrets(target_namespace: str) -> None:
    """Create or refresh preview secrets in the target namespace.

    Generated secrets are create-if-absent so a re-deploy does not rotate
    application credentials. Backup credentials are refreshed from staging on
    every deploy, then the backend is restarted so its restore init container
    observes the current mounted payload.

    Args:
        target_namespace (str): The namespace to clone secrets to.
    """
    for secret_name, fields in GENERATED_SECRET_SCHEMA.items():
        if _secret_exists(secret_name, target_namespace):
            click.echo(f"Secret {secret_name} already exists. Skipping.")
            continue
        click.echo(f"Creating least-privilege preview secret {secret_name}...")
        try:
            _create_generated_secret(secret_name, fields, target_namespace)
        except (OSError, subprocess.CalledProcessError) as e:
            click.echo(
                f"Error creating secret {secret_name}: {e}",
                err=True,
            )
            sys.exit(1)

    for secret_name in COPIED_SECRETS:
        click.echo(
            f"Refreshing {secret_name} from {SOURCE_NAMESPACE} "
            f"in {target_namespace}..."
        )
        try:
            _copy_secret_from_source(secret_name, target_namespace)
        except (
            OSError,
            subprocess.CalledProcessError,
            json.JSONDecodeError,
        ) as e:
            click.echo(
                f"Error copying secret {secret_name}: {e}",
                err=True,
            )
            sys.exit(1)

    if COPIED_SECRETS and _deployment_exists(
        "nutrition-backend", target_namespace
    ):
        try:
            subprocess.run(
                [
                    "kubectl",
                    "rollout",
                    "restart",
                    "deployment/nutrition-backend",
                    "-n",
                    target_namespace,
                ],
                check=True,
            )  # nosec: B603, B607
        except (OSError, subprocess.CalledProcessError) as e:
            click.echo(f"Error restarting preview backend: {e}", err=True)
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
