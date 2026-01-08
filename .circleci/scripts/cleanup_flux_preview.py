"""Script to clean up Flux resources on branch deletion."""

import subprocess  # nosec: B404
import sys

import click
from sanitise_branch import sanitise_branch_name


@click.command()
@click.argument("branch")
@click.option(
    "--dry-run", is_flag=True, help="Print actions instead of executing"
)
def main(branch: str, dry_run: bool) -> None:
    """Cleanup Flux Preview Environment (Pure Imperative).

    Args:
        branch (str): The branch name involved in the preview.
        dry_run (bool): If True, prints commands without executing.
    """
    if branch == "main":
        click.echo("Branch is main. Skipping cleanup.")
        sys.exit(0)

    sanitized_branch = sanitise_branch_name(branch)

    # Resources to clean up
    # 1. Kustomization (nutrition-preview-*)
    # 2. GitRepository (source-*)
    # 3. Namespace (nutrition-staging--*)

    kustomization_name = f"nutrition-preview-{sanitized_branch}"
    gitrepo_name = f"source-{sanitized_branch}"
    target_namespace = f"nutrition-staging--{sanitized_branch}"

    click.echo(
        f"Cleaning up preview environment for branch '{branch}' "
        f"(sanitized: {sanitized_branch})..."
    )

    commands = [
        (
            f"kubectl delete kustomization {kustomization_name} "
            "-n flux-system --ignore-not-found"
        ),
        (
            f"kubectl delete gitrepository {gitrepo_name} "
            "-n flux-system --ignore-not-found"
        ),
        (f"kubectl delete namespace {target_namespace} " "--ignore-not-found"),
    ]

    for cmd in commands:
        if dry_run:
            click.echo(f"[Dry Run] {cmd}")
        else:
            click.echo(f"Executing: {cmd}")
            try:
                subprocess.run(cmd.split(), check=False)  # nosec: B603
            except OSError as e:
                click.echo(f"Error executing command: {e}", err=True)

    if not dry_run:
        click.echo("Cleanup sequence completed.")


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
