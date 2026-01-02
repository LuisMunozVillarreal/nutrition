import os
import sys
import subprocess
import re
from pathlib import Path
import click
import yaml
from common import sanitize_branch_name

def generate_manifest(branch_name, image_tag, preview_domain=None):
    """Generates the content of the Flux Kustomization manifest."""
    sanitized_branch = sanitize_branch_name(branch_name)
    preview_name = f"nutrition-preview-{sanitized_branch}"
    target_namespace = f"nutrition-staging--{sanitized_branch}"
    
    # Domain Logic
    # We use Flux Variable Substitution. The domain is NOT hardcoded here.
    # It is injected by Flux at runtime from the 'cluster-settings' ConfigMap.
    # The default fallback in the script is just the variable string.
    if preview_domain:
        preview_host = preview_domain
    else:
        preview_host = f"staging--{sanitized_branch}.${{BASE_DOMAIN}}"

    manifest = f"""apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
kind: Kustomization
metadata:
  name: {preview_name}
  namespace: flux-system
spec:
  interval: 1m0s
  path: ./platform/k8s/overlays/staging
  prune: true
  wait: true
  timeout: 5m
  targetNamespace: {target_namespace}
  sourceRef:
    kind: GitRepository
    name: flux-system
  postBuild:
    substituteFrom:
      - kind: ConfigMap
        name: cluster-settings
  images:
    - name: luismunozvillarreal/nutrition-backend
      newTag: {image_tag}
    - name: luismunozvillarreal/nutrition-webapp
      newTag: {image_tag}
  patches:
    - patch: |
        - op: replace
          path: /spec/rules/0/host
          value: {preview_host}
        - op: replace
          path: /metadata/annotations/traefik.ingress.kubernetes.io~1router.tls.domains.0.main
          value: {preview_host}
      target:
        kind: Ingress
        name: .*
    - patch: |
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: nutrition-backend
        spec:
          template:
            spec:
              containers:
                - name: backend
                  env:
                    - name: ALLOWED_HOSTS
                      value: "{preview_host}"
                    - name: CSRF_TRUSTED_ORIGINS
                      value: "https://{preview_host}"
      target:
        kind: Deployment
        name: nutrition-backend
    - patch: |
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: nutrition-webapp
        spec:
          template:
            spec:
              containers:
                - name: webapp
                  env:
                    - name: GRAPHQL_ENDPOINT
                      value: "https://{preview_host}/graphql/"
                    - name: NEXTAUTH_URL
                      value: "https://{preview_host}"
      target:
        kind: Deployment
        name: nutrition-webapp
"""
    return manifest, sanitized_branch

@click.command()
@click.argument('branch')
@click.argument('tag')
@click.option('--domain', default=lambda: os.environ.get("PREVIEW_DOMAIN"), help="Override Preview Domain")
@click.option('--dry-run', is_flag=True, help="Print manifest to stdout instead of writing file")
def main(branch, tag, domain, dry_run):
    """Generate Flux Preview Manifest."""
    if branch == "main":
        click.echo("Branch is main. Skipping preview generation (handled by prod flow).")
        sys.exit(0)

    manifest_content, sanitized_branch = generate_manifest(branch, tag, domain)
    
    file_name = f"{sanitized_branch}.yaml"
    previews_dir = "platform/clusters/k3s/previews"
    file_path = f"{previews_dir}/{file_name}"
    kustomization_path = f"{previews_dir}/kustomization.yaml"
    
    if dry_run:
        click.echo(f"--- Dry Run: {file_path} ---")
        click.echo(manifest_content)
        return

    # Git Commit Logic
    try:
        subprocess.run(["git", "add", file_path, kustomization_path], check=True)
        # Check for changes
        status = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if status.returncode == 0:
            click.echo("No changes to commit.")
        else:
            subprocess.run(["git", "commit", "-m", f"[CI] Create preview env for {branch} [skip ci]"], check=True)
            click.echo("Pushed changes to git.")
            
        # Hybrid Flux: Inject GitRepository/Kustomization into Cluster (Unconditional)
        click.echo("Hybrid Flux: Applying Flux Source to Cluster...")
        
        # We need the repo URL. We can infer it or hardcode it.
        # Assuming 'origin' remote is the one.
        try:
            repo_url = subprocess.check_output(["git", "config", "--get", "remote.origin.url"]).strip().decode('utf-8')
            # Fix for Flux GitRepository validation: must be http/s or ssh
            if repo_url.startswith("git@"):
                 # Convert start 'git@github.com:' -> 'ssh://git@github.com/'
                 repo_url = "ssh://" + repo_url.replace(":", "/", 1)
        except:
            repo_url = "https://github.com/LuisMunozVillarreal/nutrition" # Fallback

        flux_source_manifest = f"""apiVersion: source.toolkit.fluxcd.io/v1beta2
kind: GitRepository
metadata:
  name: source-{sanitized_branch}
  namespace: flux-system
spec:
  interval: 1m0s
  url: {repo_url}
  ref:
    branch: {branch}
  secretRef:
    name: flux-system
---
apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
kind: Kustomization
metadata:
  name: preview-{sanitized_branch}
  namespace: flux-system
spec:
  interval: 1m0s
  path: ./platform/clusters/k3s/previews
  prune: true
  sourceRef:
    kind: GitRepository
    name: source-{sanitized_branch}
  targetNamespace: flux-system # Where the nested Kustomizations live
"""
        # Apply via kubectl
        subprocess.run(["kubectl", "apply", "-f", "-"], input=flux_source_manifest.encode('utf-8'), check=True)
        click.echo(f"Applied Flux Source 'source-{sanitized_branch}' watching branch '{branch}'.")

    except subprocess.CalledProcessError as e:
        click.echo(f"Operation failed: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
