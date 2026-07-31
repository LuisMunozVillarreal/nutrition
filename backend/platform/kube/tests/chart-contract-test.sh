#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HELM_CACHE_DIR="${SCRIPT_DIR}/.cache/helm"
HELM_BIN="${HELM_BIN:-${HELM_CACHE_DIR}/helm}"
HELM_VERSION="${HELM_VERSION:-v3.16.2}"
RENDER_DIR="$(mktemp -d)"

if [[ ! -x "$HELM_BIN" ]]; then
  if command -v helm >/dev/null 2>&1; then
    HELM_BIN="$(command -v helm)"
  else
    mkdir -p "$HELM_CACHE_DIR"
    if [[ -f "${HELM_CACHE_DIR}/helm" && ! -x "${HELM_CACHE_DIR}/helm" ]]; then
      rm -f "${HELM_CACHE_DIR}/helm"
    fi

    HELM_ARCH="$(uname -m)"
    case "${HELM_ARCH}" in
      x86_64) HELM_ARCH="amd64" ;;
      aarch64|arm64) HELM_ARCH="arm64" ;;
      *) echo "Unsupported architecture: ${HELM_ARCH}" >&2; exit 1 ;;
    esac

    echo "Helm not found, downloading ${HELM_VERSION} for linux/${HELM_ARCH} to ${HELM_BIN}..."
    curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${HELM_ARCH}.tar.gz" \
      | tar -xz -C "$HELM_CACHE_DIR" --strip-components=1 "linux-${HELM_ARCH}/helm"
  fi
fi

trap 'rm -rf "$RENDER_DIR"' EXIT

echo "Ensuring chart dependencies are present..."
"$HELM_BIN" dependency build "$CHART_DIR"

echo "Using helm binary: $HELM_BIN"
echo "Running helm lint..."
"$HELM_BIN" lint "$CHART_DIR"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" --validate > /dev/null

FULL_RENDER="$RENDER_DIR/rendered-chart.yaml"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" > "$FULL_RENDER"

if command -v kubectl >/dev/null 2>&1; then
  echo "Running manifest validation..."
  kubectl apply --dry-run=client --validate=true -f "$FULL_RENDER"
else
  echo "kubectl not found; skipping kubectl dry-run validation."
fi

DEPLOYMENT_MANIFEST_PATH="$RENDER_DIR/deployment.yaml"
SERVICE_MANIFEST_PATH="$RENDER_DIR/service.yaml"

"$HELM_BIN" template nutrition-backend "$CHART_DIR" --show-only templates/deployment.yaml > "$DEPLOYMENT_MANIFEST_PATH"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" --show-only templates/service.yaml > "$SERVICE_MANIFEST_PATH"

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if ! printf '%s\n' "$haystack" | grep -Fq -- "$needle"; then
    echo "Contract test failed: expected ${label}: ${needle}" >&2
    exit 1
  fi
}

assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "name: public" "named public listener port"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "containerPort: 8080" "public listener port 8080"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "name: health" "named health listener port"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "containerPort: 9000" "health listener port 9000"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "port: health" "liveness/readiness/startup on health port"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "runAsNonRoot: true" "non-root runtime enforcement"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "allowPrivilegeEscalation: false" "no privilege escalation"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "noNewPrivileges: true" "no-new-privileges enforcement"
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "- ALL" "restricted capabilities in deployment"
assert_contains "$(< "$SERVICE_MANIFEST_PATH")" "targetPort: public" "service target to public listener"
assert_contains "$(< "$FULL_RENDER")" "containerPort: 8080" "rendered chart exposes public listener port"

echo "Chart contract tests passed."
