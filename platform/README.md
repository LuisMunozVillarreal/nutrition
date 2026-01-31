# Platform (GitOps)

This directory contains the Infrastructure as Code (IaC) for the project, managed by **Flux CD**.

The skeleton is still created manually and `traefik` is still installed using helmfile. Check
[this](helmfile.d/README.md) for more information.

## Directory Structure

### `clusters/k3s/`
The entry point for Flux.
- **`flux-system/`**: Flux components and synchronization logic.
- **`apps.yaml`**: Main entry point for deploying applications.

### `k8s/`
Kubernetes manifests structured using **Kustomize**.
- **`base/`**: Common resources (Deployment, Service, Ingress) for Backend, Webapp, and Postgres.
- **`overlays/`**
    - **`staging`**: Configuration for Preview environments (dynamic namespace, secrets cloning).
    - **`production`**: Configuration for the Production environment (stable domain, high availability).

## Installing from scratch

### 1. Prerequisites
- A Kubernetes cluster (K3s recommended)
- `flux` CLI installed locally
- `kubectl` configured

### 2. Bootstrap Flux
Run the following command to install Flux components on your cluster:

```bash
flux bootstrap github \
  --owner=<github_username> \
  --repository=<repository_name> \
  --branch=flux \
  --path=platform/clusters/k3s \
  --personal
```

### 3. Cluster Configuration (Secrets)
To keep sensitive domains and secrets out of Git, we use **Flux Variable Substitution**.
You **MUST** create the following ConfigMap in the `flux-system` namespace:

```bash
kubectl -n flux-system create configmap cluster-settings \
  --from-literal=BASE_DOMAIN=<your-domain>
```

### 4. How it Works
1.  **Push a Branch:** CircleCI builds the Docker images.
2.  **Generate & Apply:** CI runs `.circleci/scripts/generate_flux_preview.py`. This script:
    - Generates a `GitRepository` and `Kustomization` manifest in memory.
    - Applies them **directly to the cluster** via `kubectl` (Pure Imperative).
    - **No files are committed** to the repo for previews.
3.  **Flux Sync:** Flux detects the new resources, clones the branch, substitutes `${BASE_DOMAIN}`, and creates a new Namespace (e.g., `nutrition-staging--my-branch`).
4.  **Access:** The app is available at `https://staging--my-branch.<your-domain>`.

### 5. Cleanup
We support two methods for cleanup:
1.  **Automatic (Recommended):** Deleting a branch in GitHub triggers a GitHub Action (`.github/workflows/cleanup-preview.yaml`) that runs the cleanup script.
2.  **Manual:** Run the cleanup script locally:
```bash
python3 .circleci/scripts/cleanup_flux_preview.py my-branch
```
This removes the Kustomization, GitRepository, and Namespace from the cluster.
