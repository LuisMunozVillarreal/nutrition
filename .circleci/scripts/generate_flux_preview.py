"""Script to generate Flux Kustomization manifests for preview environments."""

import os
import subprocess  # nosec: B404
import sys

import click
from common import sanitize_branch_name


def generate_manifest(
    branch_name: str, image_tag: str, preview_domain: str | None = None
) -> tuple[str, str]:
    """Generate the content of the Flux Kustomization manifest.

    Args:
        branch_name (str): The branch name for the preview.
        image_tag (str): The Docker image tag to deploy.
        preview_domain (str | None): Optional override for the ingress domain.

    Returns:
        tuple[str, str]: A tuple of (manifest_content, sanitized_branch_name).
    """
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

    annotation_path = (
        "/metadata/annotations/traefik.ingress."
        "kubernetes.io~1router.tls.domains.0.main"
    )
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
  timeout: 10m
  targetNamespace: {target_namespace}
  sourceRef:
    kind: GitRepository
    name: source-{sanitized_branch}
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
          path: {annotation_path}
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
@click.argument("branch")
@click.argument("tag")
@click.option(
    "--domain",
    default=lambda: os.environ.get("PREVIEW_DOMAIN"),
    help="Override Preview Domain",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print manifest to stdout instead of applying",
)
def main(branch: str, tag: str, domain: str | None, dry_run: bool) -> None:
    """Generate Flux Preview Manifest and Apply Directly to Cluster.

    Args:
        branch (str): The git branch name.
        tag (str): The image tag to deploy.
        domain (str | None): Optional domain override.
        dry_run (bool): If True, prints manifest without applying.
    """
    if branch == "main":
        click.echo(
            "Branch is main. Skipping preview "
            "generation (handled by prod flow)."
        )
        sys.exit(0)

    # 1. Generate the Kustomization Manifest (The "Payload")
    kustomization_content, sanitized_branch = generate_manifest(
        branch, tag, domain
    )

    # 2. Determine Repo URL for the GitRepository source
    try:
        repo_url = (
            subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"]
            )  # nosec: B607, B603
            .strip()
            .decode("utf-8")
        )
        # Fix for Flux GitRepository validation: must be http/s or ssh
        if repo_url.startswith("git@"):
            # Convert start 'git@github.com:' -> 'ssh://git@github.com/'
            repo_url = "ssh://" + repo_url.replace(":", "/", 1)
    except subprocess.CalledProcessError:
        repo_url = (
            "https://github.com/LuisMunozVillarreal/nutrition"  # Fallback
        )

    # 3. Generate the GitRepository Manifest
    git_repo_manifest = f"""apiVersion: source.toolkit.fluxcd.io/v1beta2
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
"""

    # 4. Combine Manifests
    full_manifest = f"{git_repo_manifest}---\n{kustomization_content}"

    if dry_run:
        click.echo("--- Dry Run: Applying the following to cluster ---")
        click.echo(full_manifest)
        return

    # 5. Apply to Cluster via Kubectl (Imperative)
    click.echo(f"Applying Flux resources for branch '{branch}' to cluster...")
    try:
        subprocess.run(  # nosec: B607, B603
            ["kubectl", "apply", "-f", "-"],
            input=full_manifest.encode("utf-8"),
            check=True,
        )
        click.echo(
            f"Successfully applied GitRepository 'source-{sanitized_branch}' "
            f"and Kustomization 'nutrition-preview-{sanitized_branch}'."
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Failed to apply manifests: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
