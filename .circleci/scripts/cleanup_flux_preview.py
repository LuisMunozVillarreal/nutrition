"""Script to clean up Flux resources on branch deletion."""

import subprocess  # nosec: B404
import sys
import time
from dataclasses import dataclass

import click
from sanitise_branch import sanitise_branch_name

KUSTOMIZATION_PREFIX = "nutrition-preview-"
GIT_REPO_PREFIX = "source-"
NAMESPACE_PREFIX = "nutrition-staging--"
SERVICE_ACCOUNT_PREFIX = "nutrition-preview-sa"

VERIFICATION_TIMEOUT_SECONDS = 120
VERIFICATION_POLL_SECONDS = 3


@dataclass(frozen=True)
class DeletableResource:
    """Represents a Kubernetes resource handled by the cleanup process."""

    kind: str
    namespace: str | None
    name: str

    def delete_cmd(self) -> list[str]:
        """Return the kubectl command used to delete this resource.

        Returns:
            list[str]: kubectl args that delete this resource.
        """
        cmd = ["kubectl", "delete", self.kind, self.name]
        if self.namespace:
            cmd.extend(["-n", self.namespace])
        cmd.append("--ignore-not-found")
        return cmd

    def exists_cmd(self) -> list[str]:
        """Return the kubectl command used to check this resource exists.

        Returns:
            list[str]: kubectl args that check this resource exists.
        """
        cmd = ["kubectl", "get", self.kind, self.name]
        if self.namespace:
            cmd.extend(["-n", self.namespace])
        return cmd


def _preview_kustomization_name(sanitized_branch: str) -> str:
    return f"{KUSTOMIZATION_PREFIX}{sanitized_branch}"


def _preview_git_repo_name(sanitized_branch: str) -> str:
    return f"{GIT_REPO_PREFIX}{sanitized_branch}"


def _preview_namespace_name(sanitized_branch: str) -> str:
    return f"{NAMESPACE_PREFIX}{sanitized_branch}"


def _preview_service_account_name(sanitized_branch: str) -> str:
    return f"{SERVICE_ACCOUNT_PREFIX}-{sanitized_branch}"


def _iter_resources(sanitized_branch: str) -> list[DeletableResource]:
    namespace = _preview_namespace_name(sanitized_branch)
    return [
        DeletableResource(
            "kustomization",
            "flux-system",
            _preview_kustomization_name(sanitized_branch),
        ),
        DeletableResource(
            "gitrepository",
            "flux-system",
            _preview_git_repo_name(sanitized_branch),
        ),
        DeletableResource(
            "serviceaccount",
            "flux-system",
            _preview_service_account_name(sanitized_branch),
        ),
        DeletableResource("namespace", None, namespace),
    ]


def _delete_resources(resources: list[DeletableResource]) -> tuple[bool, str]:
    for resource in resources:
        command = resource.delete_cmd()
        click.echo(f"Executing: {' '.join(command)}")
        try:
            result = subprocess.run(  # nosec: B603, B607
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:  # pragma: no cover - integration failure path
            return (
                False,
                f"Error deleting {resource.kind} '{resource.name}': {exc}",
            )

        if result.returncode != 0:
            message = (
                result.stderr or result.stdout or "unknown error"
            ).strip()
            return (
                False,
                (
                    "Failed to delete "
                    f"{resource.kind} '{resource.name}' in "
                    f"namespace '{resource.namespace or 'cluster'}': {message}"
                ),
            )
    return True, ""


def _resource_exists(resource: DeletableResource) -> tuple[bool, str]:
    result = subprocess.run(  # nosec: B603, B607
        resource.exists_cmd(),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        return True, ""

    message = (result.stdout + result.stderr).lower()
    if "not found" in message:
        return False, ""

    details = (result.stderr or result.stdout or "unknown error").strip()
    return (
        False,
        f"Unable to verify deletion of {resource.kind} '{resource.name}': {details}",
    )


def _wait_for_absent(resource: DeletableResource) -> tuple[bool, str]:
    deadline = time.time() + VERIFICATION_TIMEOUT_SECONDS
    while time.time() < deadline:
        exists, msg = _resource_exists(resource)
        if msg:
            return False, msg
        if not exists:
            return True, ""

        click.echo(
            f"Waiting for {resource.kind} '{resource.name}' to disappear..."
        )
        time.sleep(VERIFICATION_POLL_SECONDS)

    return False, f"Timed out waiting for {resource.kind} '{resource.name}'."


def _verify_absent(resources: list[DeletableResource]) -> tuple[bool, str]:
    for resource in resources:
        deleted, msg = _wait_for_absent(resource)
        if not deleted:
            return False, msg
    return True, ""


@click.command()
@click.argument("branch")
@click.option(
    "--dry-run", is_flag=True, help="Print actions instead of executing"
)
def main(branch: str, dry_run: bool) -> None:
    """Cleanup Flux Preview Environment (Pure Imperative).

    Args:
        branch (str): The branch being deleted.
        dry_run (bool): Whether to print commands without executing them.
    """
    if branch == "main":
        click.echo("Branch is main. Skipping cleanup.")
        sys.exit(0)

    sanitized_branch = sanitise_branch_name(branch)

    click.echo(
        f"Cleaning up preview environment for branch '{branch}' "
        f"(sanitized: {sanitized_branch})..."
    )

    resources = _iter_resources(sanitized_branch)

    if dry_run:
        for resource in resources:
            click.echo(f"[Dry Run] {' '.join(resource.delete_cmd())}")
        return

    success, error = _delete_resources(resources)
    if not success:
        click.echo(error, err=True)
        click.echo("Cleanup sequence failed.", err=True)
        sys.exit(1)

    verified, verify_error = _verify_absent(resources)
    if not verified:
        click.echo(verify_error, err=True)
        click.echo("Cleanup sequence failed.", err=True)
        sys.exit(1)

    click.echo("Cleanup sequence completed.")


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
