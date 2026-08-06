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

The Garmin synchronization CronJob is suspended by default in the base, staging,
and production Kustomize renders. Do not add an activation patch until runtime
configuration explicitly enables Garmin in both the backend and CronJob and
supplies all credential, provider endpoint/origin, and callback URL/origin
values. Committed manifests must retain neutral placeholders rather than real
provider or deployment endpoints.
