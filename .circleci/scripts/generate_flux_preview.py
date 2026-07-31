"""Script to generate Flux Kustomization manifests for preview environments."""

import os
import subprocess  # nosec: B404
import sys

import click
from sanitise_branch import sanitise_branch_name

KUSTOMIZATION_PREFIX = "nutrition-preview-"
GIT_REPO_PREFIX = "source-"
SERVICE_ACCOUNT_PREFIX = "nutrition-preview-sa"
ROLE_PREFIX = "nutrition-preview-rbac"
NAMESPACE_PREFIX = "nutrition-staging--"
TRUSTED_SOURCE_BRANCH = "main"


def _preview_service_account_name(sanitized_branch: str) -> str:
    return f"{SERVICE_ACCOUNT_PREFIX}-{sanitized_branch}"


def _preview_role_name(sanitized_branch: str) -> str:
    return f"{ROLE_PREFIX}-{sanitized_branch}"


def _preview_namespace_name(sanitized_branch: str) -> str:
    return f"{NAMESPACE_PREFIX}{sanitized_branch}"


def _build_preview_rbac(namespace: str, sanitized_branch: str) -> str:
    """Generate RBAC objects used by Flux preview reconciliation."""
    service_account_name = _preview_service_account_name(sanitized_branch)
    role_name = _preview_role_name(sanitized_branch)

    return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {service_account_name}
  namespace: flux-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: {role_name}
  namespace: {namespace}
rules:
  - apiGroups: [""]
    resources:
      - "*"
    verbs:
      - create
      - delete
      - deletecollection
      - get
      - list
      - patch
      - update
      - watch
  - apiGroups: ["*"]
    resources:
      - "*"
    verbs:
      - create
      - delete
      - deletecollection
      - get
      - list
      - patch
      - update
      - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: {role_name}
  namespace: {namespace}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: {role_name}
subjects:
  - kind: ServiceAccount
    name: {service_account_name}
    namespace: flux-system
"""


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
    sanitized_branch = sanitise_branch_name(branch_name)
    preview_name = f"{KUSTOMIZATION_PREFIX}{sanitized_branch}"
    target_namespace = _preview_namespace_name(sanitized_branch)
    service_account_name = _preview_service_account_name(sanitized_branch)

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
  serviceAccountName: {service_account_name}
  wait: true
  timeout: 10m
  targetNamespace: {target_namespace}
  sourceRef:
    kind: GitRepository
    name: {GIT_REPO_PREFIX}{sanitized_branch}
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
    target_namespace = _preview_namespace_name(sanitized_branch)
    rbac_content = _build_preview_rbac(target_namespace, sanitized_branch)
    kustomization_name = f"{KUSTOMIZATION_PREFIX}{sanitized_branch}"
    service_account_name = _preview_service_account_name(sanitized_branch)

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
  name: {GIT_REPO_PREFIX}{sanitized_branch}
  namespace: flux-system
spec:
  interval: 1m0s
  url: {repo_url}
  ref:
    branch: {TRUSTED_SOURCE_BRANCH}
  secretRef:
    name: flux-system
"""

    # 4. Combine Manifests
    full_manifest = (
        f"{rbac_content}---\n{git_repo_manifest}---\n{kustomization_content}"
    )

    if dry_run:
        click.echo("--- Dry Run: Applying the following to cluster ---")
        click.echo(full_manifest)
        return

    # 5. Apply to Cluster via Kubectl (Imperative)
    click.echo(
        f"Applying Flux resources for branch '{branch}' to "
        f"cluster (preview '{sanitized_branch}')..."
    )
    try:
        subprocess.run(  # nosec: B607, B603
            ["kubectl", "apply", "-f", "-"],
            input=full_manifest.encode("utf-8"),
            check=True,
        )
        click.echo(
            "Successfully applied namespace, service account, "
            f"GitRepository '{GIT_REPO_PREFIX}{sanitized_branch}' "
            f"and Kustomization '{kustomization_name}' "
            f"as '{service_account_name}'."
        )
    except subprocess.CalledProcessError as e:
        click.echo(f"Failed to apply manifests: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()  # pylint: disable=no-value-for-parameter
