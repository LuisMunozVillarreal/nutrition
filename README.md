# Local development

## Backend

Check [these instructions](backend/README.md)

## Samsung Health step sync

The Android companion in [`android-health-sync/`](android-health-sync/) reads daily
step aggregates from Health Connect and uploads them with a revocable, step-only
device credential. Device credentials expire after 180 days and can be revoked from
the steps page. Production must configure a dedicated
`HEALTH_SYNC_TOKEN_PEPPER`; during rotation, place prior values in the
comma-separated `HEALTH_SYNC_TOKEN_PEPPER_FALLBACKS` setting until active
devices have rehashed. Pairing throttles use Django's cache, so production must
use a shared cache backend and also enforce request/body limits at the reverse
proxy. When deployed behind trusted proxies, set
`HEALTH_SYNC_TRUSTED_PROXY_COUNT` to the exact number of proxies that overwrite
the forwarded-address chain and list the direct proxy networks in
`HEALTH_SYNC_TRUSTED_PROXY_CIDRS`; leave both empty/zero when clients connect
directly. Production startup fails closed unless `CACHE_URL` selects Redis and
`HEALTH_SYNC_TOKEN_PEPPER` differs from `SECRET_KEY`. Staging previews reconcile
the PR branch's own Kubernetes manifests with the branch image tags and
compatibility patches, so they may temporarily use the process-local
cache while CI injects an independent preview pepper. Uploads
are also bounded globally, by client address, and per paired device. Kubernetes
deployments must provision the `nutrition-health-sync-secrets` Secret with
independent `token-pepper` and `trusted-proxy-cidrs` keys before rollout. During
pepper rotation, its optional `token-pepper-fallbacks` key contains the prior
values until the 180-day device-token lifetime has elapsed; the CIDR value must
identify only the direct trusted proxy network. The base manifests include an
internal, non-persistent Redis cache used only for rate limits.

Samsung Health must be configured to share step data with Health Connect. See
the companion README for build, pairing, permission, and sync instructions.

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
# Replace 'example.com' with your actual base domain
kubectl -n flux-system create configmap cluster-settings \
  --from-literal=BASE_DOMAIN=example.com
```

### 4. How it Works
1.  **Push a Branch:** CircleCI builds the Docker images.
2.  **Generate & Apply:** CI runs `.circleci/scripts/generate_flux_preview.py`. This script:
    - Generates a `GitRepository` and `Kustomization` manifest in memory.
    - Applies them **directly to the cluster** via `kubectl` (Pure Imperative).
    - **No files are committed** to the repo for previews.
3.  **Flux Sync:** Flux detects the new resources, reconciles the PR branch's own Kubernetes manifests with the branch image tags and compatibility patches, substitutes `${BASE_DOMAIN}`, and creates a new Namespace (e.g., `nutrition-staging--my-branch`).
4.  **Access:** The app is available at `https://staging--my-branch.example.com`.

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
