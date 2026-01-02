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
    else:
        if dry_run:
            click.echo(f"--- Dry Run: Delete {file_path} ---")
        else:
            os.remove(file_path)
            click.echo(f"Deleted {file_path}")

    # Remove from kustomization.yaml
    if os.path.exists(kustomization_path):
        try:
            with open(kustomization_path, 'r') as f:
                kust_data = yaml.safe_load(f) or {}
            
            resources = kust_data.get('resources', [])
            if file_name in resources:
                if dry_run:
                    click.echo(f"--- Dry Run: Remove {file_name} from {kustomization_path} ---")
                else:
                    resources.remove(file_name)
                    kust_data['resources'] = resources
                    with open(kustomization_path, 'w') as f:
                        yaml.dump(kust_data, f, default_flow_style=False)
                    click.echo(f"Removed {file_name} from {kustomization_path}")
                    
                    # Add kustomization.yaml to git
                    if not dry_run:
                        subprocess.run(["git", "add", kustomization_path], check=True)

        except Exception as e:
            click.echo(f"Error updating kustomization.yaml: {e}", err=True)

    if dry_run:
        return

    # Git Commit Logic
    try:
        if os.path.exists(file_path): # Should be gone, but check if we need to git rm
             subprocess.run(["git", "add", file_path], check=True)
        else:
             # It's deleted, git add will record the deletion
             subprocess.run(["git", "add", file_path], check=False) # check=False in case it was already untracked

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
