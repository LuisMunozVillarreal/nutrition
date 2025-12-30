# Platform (GitOps)

This directory contains the Infrastructure as Code (IaC) for the project, managed by **Flux CD**.

## Directory Structure

### `clusters/k3s/`
The entry point for Flux.
- **`flux-system/`**: Flux components and synchronization logic.
- **`apps.yaml`**: Main entry point for deploying applications.
- **`previews/`**: Contains dynamically generated Kustomization files for feature branches.

### `k8s/`
Kubernetes manifests structured using **Kustomize**.
- **`base/`**: Common resources (Deployment, Service, Ingress) for Backend, Webapp, and Postgres.
- **`overlays/`**
    - **`staging`**: Configuration for Preview environments (dynamic namespace, secrets cloning).
    - **`production`**: Configuration for the Production environment (stable domain, high availability).

## How to add a new resource
1.  Add the YAML file to `k8s/base/`.
2.  Add it to `resources` in `k8s/base/kustomization.yaml`.
3.  (Optional) Add environment-specific patches in `k8s/overlays/<env>/kustomization.yaml`.

