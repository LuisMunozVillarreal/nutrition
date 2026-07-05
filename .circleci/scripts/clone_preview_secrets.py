"""Script to clone Kubernetes secrets to preview namespaces in CI."""

import json
import subprocess  # nosec: B404
import sys
import time

import click
from sanitise_branch import sanitise_branch_name

SECRETS = [
    "nutrition-webapp-nextauth-secret",
    "nutrition-postgresql",
    "nutrition-django-secret-key",
    "nutrition-gemini-api-key",
    "nutrition-gcp-db-backup-credentials",
]
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


def clone_secrets(target_namespace: str) -> None:
    """Clone the required secrets to the target namespace.

    Args:
        target_namespace (str): The namespace to clone secrets to.
    """
    for secret in SECRETS:
        click.echo(
            f"Copying {secret} from {SOURCE_NS} to {target_namespace}..."
        )
        try:
            res = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "secret",
                    secret,
                    "-n",
                    SOURCE_NS,
                    "-o",
                    "json",
                ],
                capture_output=True,
                check=True,
            )  # nosec: B603, B607
            secret_data = json.loads(res.stdout)

            metadata = secret_data.get("metadata", {})
            for key in [
                "namespace",
                "resourceVersion",
                "uid",
                "creationTimestamp",
                "ownerReferences",
            ]:
                metadata.pop(key, None)

            subprocess.run(
                ["kubectl", "apply", "-n", target_namespace, "-f", "-"],
                input=json.dumps(secret_data).encode("utf-8"),
                check=True,
            )  # nosec: B603, B607

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            click.echo(
                f"Error cloning secret {secret}: {e}",
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

    wait_for_namespace(target_namespace)
    clone_secrets(target_namespace)


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
