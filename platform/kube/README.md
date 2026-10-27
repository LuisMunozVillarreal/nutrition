# Legacy chart tooling

Production, staging and previews use the application Flux/Kustomize installation
in [platform/README.md](../README.md). Do not install the legacy app charts as a
second copy of Nutrition. The old application Helmfile and environment templates
were unused by the active Flux deployment and have been removed.

Shared Traefik installation and its additional providers now live in
[LuisMunozVillarreal/htpc-flux](https://github.com/LuisMunozVillarreal/htpc-flux).
Its pinned HelmRelease replaces `helmfile.d/00-traefik.yaml` after read-only
structure/value parity checks. Real settings and secrets remain outside Git.

Existing clusters must complete htpc-flux's `docs/migration.md` cutover before
merging the old cluster-tree deletion. Do not apply a Helmfile, install CRDs
manually, overwrite ACME data or uninstall the shared ingress release.

The backend chart remains for its existing contract tests. It is not the current
production installation entry point. The historical SQL file is not consumed by
the current PostgreSQL Deployment; never add credentials to it.
