import os
import sys
import subprocess
import shutil
import click

def sanitize_branch_name(branch_name):
    """Sanitizes the branch name to be K8s/DNS compatible."""
    s = branch_name.lower()
    s = s.replace('/', '-')
    s = s.replace('_', '-')
    return s

@click.command()
@click.argument('branch')
@click.option('--dry-run', is_flag=True, help="Print actions instead of executing")
def main(branch, dry_run):
    """Cleanup Flux Preview Environment."""
    if branch == "main":
        click.echo("Branch is main. Skipping cleanup.")
        sys.exit(0)

    sanitized_branch = sanitize_branch_name(branch)
    file_path = f"platform/clusters/k3s/previews/{sanitized_branch}.yaml"
    
    if not os.path.exists(file_path):
        click.echo(f"Preview manifest {file_path} not found. Nothing to cleanup.")
        sys.exit(0)

    if dry_run:
        click.echo(f"--- Dry Run: Delete {file_path} ---")
        return

    # Delete file
    os.remove(file_path)
    click.echo(f"Deleted {file_path}")
    
    # Git Commit Logic
    try:
        subprocess.run(["git", "add", file_path], check=True)
        # Check for changes (deletion is a change)
        status = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if status.returncode == 0:
             click.echo("No changes to commit (file might have been ignored or already gone).")
        else:
            subprocess.run(["git", "commit", "-m", f"[CI] Cleanup preview env for {branch} [skip ci]"], check=True)
            subprocess.run(["git", "push", "origin", "HEAD"], check=True)
            click.echo("Pushed cleanup commit to git.")
    except subprocess.CalledProcessError as e:
        click.echo(f"Git operation failed: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
