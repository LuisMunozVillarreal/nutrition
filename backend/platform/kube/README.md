# Legacy API chart

Do not install this chart as a second copy of the API. Current production,
staging and previews use the application manifests documented in
[the platform installation guide](../../../platform/README.md).
Shared Flux and Traefik infrastructure belongs to the separate htpc-flux repo.

This chart is retained for compatibility and the existing chart-contract tests.
For chart-only dependency development, `helm dependency update` regenerates its
lock file. It is not an instruction to change the production deployment.
