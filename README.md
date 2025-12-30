# Local development

## Backend

Check [these instructions](backend/README.md)

## Deploy to production

Check [these instructions](platform/README.md)

## Flux CD & Dynamic Environments

This repository uses **Flux CD** to manage deployments and create dynamic preview environments for every branch.

### 1. Prerequisites
- A Kubernetes cluster (K3s recommended)
- `flux` CLI installed locally
- `kubectl` configured

### 2. Bootstrap Flux
Run the following command to install Flux components on your cluster:

```bash
flux bootstrap github \
  --owner=LuisMunozVillarreal \
  --repository=nutrition \
  --branch=flux \
  --path=platform/clusters/k3s \
  --personal
```

### 3. Cluster Configuration (Secrets)
To keep sensitive domains and secrets out of Git, we use **Flux Variable Substitution**.
You **MUST** create the following ConfigMap in the `flux-system` namespace:

```bash
# Replace 'nutfeex.ddns.net' with your actual base domain
kubectl -n flux-system create configmap cluster-settings \
  --from-literal=BASE_DOMAIN=nutfeex.ddns.net
```

### 4. How it Works
1.  **Push a Branch:** CircleCI builds the Docker images.
2.  **Generate & Apply:** CI runs `.circleci/scripts/generate_flux_preview.py`. This script:
    - Generates a `GitRepository` and `Kustomization` manifest in memory.
    - Applies them **directly to the cluster** via `kubectl` (Pure Imperative).
    - **No files are committed** to the repo for previews.
3.  **Flux Sync:** Flux detects the new resources, clones the branch, substitutes `${BASE_DOMAIN}`, and creates a new Namespace (e.g., `nutrition-staging--my-branch`).
4.  **Access:** The app is available at `https://staging--my-branch.nutfeex.ddns.net`.

### 5. Cleanup
We support two methods for cleanup:
1.  **Automatic (Recommended):** Deleting a branch in GitHub triggers a GitHub Action (`.github/workflows/cleanup-preview.yaml`) that runs the cleanup script.
2.  **Manual:** Run the cleanup script locally:
```bash
python3 .circleci/scripts/cleanup_flux_preview.py my-branch
```
This removes the Kustomization, GitRepository, and Namespace from the cluster.


# CI Config
Kubeconfig is expected to be in the `KUBECONFIG_DATA_BASE64` environment variable for both CircleCI and GitHub Actions.

To create the contento of the variable, execute:
```bash
base64 -w 0 ~/.kube/config > kubeconfig
```
