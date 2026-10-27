# Nutrition application GitOps

This repository installs Nutrition only. Shared k3s, Flux bootstrap, Traefik
installation and additional file-provider routes belong to
[LuisMunozVillarreal/htpc-flux](https://github.com/LuisMunozVillarreal/htpc-flux).

## Preinstalled prerequisites

- Kubernetes with Flux controllers and source/kustomize CRDs already installed.
  The migration retains Flux v2.7.5, not an incidental upgrade.
- Traefik already installed with Kubernetes Ingress and CRD providers, the
  `traefik.containo.us` Middleware CRDs used by the current app, `websecure`, and
  the `letsencrypt` resolver. The shared repository retains chart 26.0.0 and
  app v2.10.6. Do not install a second controller from this repository.
- A default storage class, currently k3s `local-path`. Production uses the
  existing 8Gi `nutrition-postgres-data` PVC. A PVC manifest is not a data backup.
- `flux-system/cluster-settings` ConfigMap with a private `BASE_DOMAIN` value.
- `flux-system/nutrition-git` SSH Secret with `identity`, `identity.pub` and
  `known_hosts`, authorized to read this repository and preview branches.
  The cluster-owned `flux-system` GitRepository and Secret are not app sources.

## Entry points and installation

`k8s/base` and `k8s/overlays/{production,staging}` are the app workloads.
`flux/source.yaml` creates GitRepository `nutrition` on main.
`flux/apps` creates the application namespaces and the stable
`nutrition-production` and `nutrition-staging` Flux Kustomizations.
`flux/kustomization.yaml` combines these into a standalone app installation.

For a new app installation on a prepared cluster, create the namespaces first:

```sh
kubectl apply -f platform/flux/apps/namespaces.yaml
```

Provision the following Secrets in **both** namespaces using private files or
an existing secret store. Never put their values, deployment identifiers,
kubeconfig, database dumps or backup data in Git.

| Secret | Required keys |
| --- | --- |
| `nutrition-postgresql` | `postgresql-password` |
| `nutrition-gemini-api-key` | `gemini-api-key` |
| `nutrition-django-secret-key` | `secret-key` |
| `nutrition-webapp-nextauth-secret` | `nextauth-secret` |
| `nutrition-gcp-db-backup-credentials` | `nutrition-gcp-db-backup-credentials.json` |
| `nutrition-health-sync-secrets` | `token-pepper`, `trusted-proxy-cidrs`; optional `token-pepper-fallbacks` |

The active PostgreSQL Deployment does not consume the legacy Helm init-script
Secret. Do not edit a tracked SQL file to hold a password. Backup credentials
need external object-store access; staging restores from that store. A fresh
production PVC is empty, not a restored database.

Choose one owner for the app entry points:

- With htpc-flux, its root owns GitRepository `nutrition` and Kustomization
  `nutrition-apps`, whose path is `./platform/flux/apps`. Follow that repository's
  activation runbook; do not also reconcile the combined entry from another root.
- For an independently operated cluster with all prerequisites already met,
  an authorized operator can run `kubectl apply -k platform/flux` and then let
  the two app Kustomizations reconcile. No cluster bootstrap is installed by it.

Before the first rollout, select the approved image SHA via the existing CI
process. App entry manifests omit `spec.images` deliberately; CircleCI owns both
image tags and patches the same Kustomization names. No image automation is added.
Do not assume an absent image override means an approved version was selected.

## Existing-cluster migration warning

**Do not merge this extraction before the old root has been suspended and its
pruning disabled.** The old root points at `platform/clusters/k3s` with
`prune: true`. The staged procedure is in htpc-flux's `docs/migration.md`.
Provision `nutrition-git` and switch existing main/preview sources before rotating
the cluster Git credential. Preserve image tags, app suspension state and PVCs.
No live migration or recovery drill is performed by this PR.

## Preview and CI contract

Preview GitRepositories still track their own PR branches. They now authenticate
with `nutrition-git`, not the cluster bootstrap key. Existing previews must have
their Secret reference migrated before the old key is replaced. Namespace-scoped
preview RBAC, target namespaces, settings substitution and image selection are
unchanged. Keep `KUBECONFIG_DATA_BASE64` in CircleCI and the branch-cleanup GitHub
Action's external secret store, not in either repository.

The migration branch is published with `[skip ci]` to avoid an unauthorized live
preview deployment. After operator approval and credential preparation, run the
normal CI pipeline and verify terminal preview and E2E jobs before calling it
ready for deployment.

## Offline verification

With Python 3, PyYAML, pytest, pytest-mock, click and kubectl installed:

```sh
python3 -m unittest discover -s platform/tests -v
python3 -m pytest .circleci/scripts/ -q
```

The app contract renders both overlays and the standalone Flux entry without
contacting the Kubernetes API. The preflight suite below is also stdlib-only.

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
