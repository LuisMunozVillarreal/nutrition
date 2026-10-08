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

## Main deployment preflight

Both main-branch staging and production rollouts run
`.circleci/scripts/deployment_preflight.py` before patching images. It only reads
Flux Kustomizations and the required Secrets in the target namespace. A suspended
Kustomization blocks deployment: an operator must decide when to explicitly
resume it using the instruction in the failure message, then rerun deployment.
CI never resumes it automatically.

The preflight checks required keys for Django, Gemini, PostgreSQL, NextAuth,
mounted backup credentials, and health-sync. Health-sync needs a nonempty
`token-pepper` distinct from Django's `secret-key`, plus nonempty comma-separated
IPv4/IPv6 `trusted-proxy-cidrs` with no universal `/0` network. Optional
`token-pepper-fallbacks` are not required. Supply real values through the existing
Secret management process; never put them in repository files or logs.
Failures report only fixed resource/key identifiers, never Secret values or raw
kubectl errors. A passing preflight checks prerequisites, not rollout readiness.

The shipped backend has two proxy hops: ingress, then container-local nginx.
Nginx appends its peer to `X-Forwarded-For`, so the base manifest uses
`HEALTH_SYNC_TRUSTED_PROXY_COUNT=2`. The direct peer seen by Django is nginx's
loopback connection, not the ingress pod network. Provision `trusted-proxy-cidrs`
for that verified local peer. If the proxy topology changes, re-evaluate both
settings together rather than trusting a broad cluster network.

The explicit key contract is checked against deployment manifests by stdlib
unittest tests in the `chart-contract-tests` CI job. Run them locally without
cluster access:

```sh
python3 -m unittest discover -s .circleci/scripts -p 'test_deployment_preflight.py'
```
