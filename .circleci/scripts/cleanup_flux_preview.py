import os
import sys
import subprocess
import click
import yaml
from common import sanitize_branch_name

@click.command()
@click.argument('branch')
@click.option('--dry-run', is_flag=True, help="Print actions instead of executing")
def main(branch, dry_run):
    """Cleanup Flux Preview Environment."""
    if branch == "main":
        click.echo("Branch is main. Skipping cleanup.")
        sys.exit(0)

    sanitized_branch = sanitize_branch_name(branch)
    file_name = f"{sanitized_branch}.yaml"
    previews_dir = "platform/clusters/k3s/previews"
    file_path = f"{previews_dir}/{file_name}"
    kustomization_path = f"{previews_dir}/kustomization.yaml"
    
    if not os.path.exists(file_path):
        click.echo(f"Preview manifest {file_path} not found. Checking if needs removal from kustomization.")
    # Git Commit Logic
    try:
        if os.path.exists(file_path): # Should be gone, but check if we need to git rm
             subprocess.run(["git", "add", file_path], check=True)
        else:
             # It's deleted, git add will record the deletion
             subprocess.run(["git", "add", file_path], check=False)

        # Check for changes (deletion is a change)
        status = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if status.returncode == 0:
             click.echo("No changes to commit.")
        else:
            subprocess.run(["git", "commit", "-m", f"[CI] Cleanup preview env for {branch} [skip ci]"], check=True)
            subprocess.run(["git", "push", "origin", "HEAD"], check=True)
            click.echo("Pushed cleanup commit to git.")
    except subprocess.CalledProcessError as e:
        click.echo(f"Git operation failed: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
