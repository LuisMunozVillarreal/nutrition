# Platform (GitOps)

This directory contains the Infrastructure as Code (IaC) for the project, managed by **Flux CD**.

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
