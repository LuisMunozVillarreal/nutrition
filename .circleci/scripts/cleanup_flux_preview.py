import os
import sys
import subprocess
import click
from common import sanitize_branch_name

@click.command()
@click.argument('branch')
@click.option('--dry-run', is_flag=True, help="Print actions instead of executing")
def main(branch, dry_run):
    """Cleanup Flux Preview Environment (Pure Imperative)."""
    if branch == "main":
        click.echo("Branch is main. Skipping cleanup.")
        sys.exit(0)

    sanitized_branch = sanitize_branch_name(branch)
    
    # Resources to clean up
    # 1. Kustomization (nutrition-preview-*)
    # 2. GitRepository (source-*)
    # 3. Namespace (nutrition-staging--*)
    
    kustomization_name = f"nutrition-preview-{sanitized_branch}"
    gitrepo_name = f"source-{sanitized_branch}"
    target_namespace = f"nutrition-staging--{sanitized_branch}"

    click.echo(f"Cleaning up preview environment for branch '{branch}' (sanitized: {sanitized_branch})...")

    commands = [
        f"kubectl delete kustomization {kustomization_name} -n flux-system --ignore-not-found",
        f"kubectl delete gitrepository {gitrepo_name} -n flux-system --ignore-not-found",
        f"kubectl delete namespace {target_namespace} --ignore-not-found"
    ]

    for cmd in commands:
        if dry_run:
            click.echo(f"[Dry Run] {cmd}")
        else:
            click.echo(f"Executing: {cmd}")
            try:
                subprocess.run(cmd.split(), check=False)
            except Exception as e:
                click.echo(f"Error executing command: {e}", err=True)

    if not dry_run:
        click.echo("Cleanup sequence completed.")

if __name__ == "__main__":
    main()
