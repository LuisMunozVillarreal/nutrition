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
`token-pepper` distinct from Django's `secret-key`. Both must be literal values,
not environment references. Proxy configuration needs nonempty comma-separated
IPv4/IPv6 `trusted-proxy-cidrs` with no whitespace, host bits, or universal `/0`
network. Optional
`token-pepper-fallbacks` are not required. Supply real values through the existing
Secret management process; never put them in repository files or logs.
Failures report only fixed resource/key identifiers, never Secret values or raw
kubectl errors. A passing preflight checks prerequisites, not rollout readiness.

The shipped backend includes container-local nginx, which connects to Django
through loopback and appends its upstream peer to `X-Forwarded-For`. Provision
`trusted-proxy-cidrs` for the verified direct peer, not a guessed cluster network.
The existing one-hop count conservatively groups ingress traffic by that upstream
proxy. Do not increase it merely to recover the original client address: first
restrict or validate upstream access so direct Service callers cannot spoof
additional forwarded entries. This preflight does not validate network topology.

The explicit key contract is checked against deployment manifests by stdlib
unittest tests in the `chart-contract-tests` CI job. Run them locally without
cluster access:

```sh
python3 -m unittest discover -s .circleci/scripts -p 'test_deployment_preflight.py'
```
