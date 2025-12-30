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
2.  **Generate Manifest:** CI runs `.circleci/scripts/generate_flux_preview.py` to create a new Kustomize file in `platform/clusters/k3s/previews/`.
3.  **Flux Sync:** Flux detects the commit, substitutes `${BASE_DOMAIN}`, and creates a new Namespace (e.g., `nutrition-staging--my-branch`).
4.  **Access:** The app is available at `https://staging--my-branch.nutfeex.ddns.net`.

### 5. Cleanup
When you are done with a branch, run the cleanup script (or let CI handle it if configured):
```bash
python3 .circleci/scripts/cleanup_flux_preview.py my-branch
```
