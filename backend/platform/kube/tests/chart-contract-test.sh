#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HELM_CACHE_DIR="${SCRIPT_DIR}/.cache/helm"
KUBECONFORM_CACHE_DIR="${SCRIPT_DIR}/.cache/kubeconform"
HELM_BIN="${HELM_BIN:-${HELM_CACHE_DIR}/helm}"
KUBECONFORM_BIN="${KUBECONFORM_BIN:-${KUBECONFORM_CACHE_DIR}/kubeconform}"
HELM_VERSION="${HELM_VERSION:-v3.16.2}"
KUBECONFORM_VERSION="${KUBECONFORM_VERSION:-v0.8.0}"
KUBERNETES_VERSION="${KUBERNETES_VERSION:-1.33.0}"
RENDER_DIR="$(mktemp -d)"

if [[ ! -x "$HELM_BIN" ]]; then
  if [[ "${HELM_INSTALL_ONLY:-0}" != "1" ]] && command -v helm >/dev/null 2>&1; then
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

    HELM_URL="https://get.helm.sh/helm-${HELM_VERSION}-linux-${HELM_ARCH}.tar.gz"
    echo "Helm not found, downloading ${HELM_VERSION} for linux/${HELM_ARCH} to ${HELM_BIN}..."
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$HELM_URL" \
        | tar -xz -C "$HELM_CACHE_DIR" --strip-components=1 "linux-${HELM_ARCH}/helm"
    else
      HELM_ARCHIVE="${HELM_CACHE_DIR}/helm.tar.gz"
      python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
        "$HELM_URL" "$HELM_ARCHIVE"
      tar -xzf "$HELM_ARCHIVE" -C "$HELM_CACHE_DIR" --strip-components=1 "linux-${HELM_ARCH}/helm"
      rm -f "$HELM_ARCHIVE"
    fi
  fi
fi

if [[ "${HELM_INSTALL_ONLY:-0}" == "1" ]]; then
  exit 0
fi

if [[ ! -x "$KUBECONFORM_BIN" ]]; then
  if command -v kubeconform >/dev/null 2>&1; then
    KUBECONFORM_BIN="$(command -v kubeconform)"
  else
    mkdir -p "$KUBECONFORM_CACHE_DIR"
    if [[ -f "${KUBECONFORM_CACHE_DIR}/kubeconform" && ! -x "${KUBECONFORM_CACHE_DIR}/kubeconform" ]]; then
      rm -f "${KUBECONFORM_CACHE_DIR}/kubeconform"
    fi

    KUBECONFORM_ARCH="$(uname -m)"
    case "${KUBECONFORM_ARCH}" in
      x86_64) KUBECONFORM_ARCH="amd64" ;;
      aarch64|arm64) KUBECONFORM_ARCH="arm64" ;;
      *) echo "Unsupported architecture: ${KUBECONFORM_ARCH}" >&2; exit 1 ;;
    esac

    echo "kubeconform not found, downloading ${KUBECONFORM_VERSION} for linux/${KUBECONFORM_ARCH} to ${KUBECONFORM_BIN}..."
    curl -fsSL "https://github.com/yannh/kubeconform/releases/download/${KUBECONFORM_VERSION}/kubeconform-linux-${KUBECONFORM_ARCH}.tar.gz" \
      | tar -xz -C "$KUBECONFORM_CACHE_DIR"
  fi
fi
chmod +x "$KUBECONFORM_BIN"

trap 'rm -rf "$RENDER_DIR"' EXIT

echo "Ensuring chart dependencies are present..."
"$HELM_BIN" dependency build "$CHART_DIR"

echo "Using helm binary: $HELM_BIN"
echo "Running helm lint..."
"$HELM_BIN" lint "$CHART_DIR"

FULL_RENDER="$RENDER_DIR/rendered-chart.yaml"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" > "$FULL_RENDER"

if command -v kubectl >/dev/null 2>&1; then
  echo "Running manifest validation..."
  kubectl apply --dry-run=client --validate=true -f "$FULL_RENDER"
else
  echo "kubectl not found; skipping kubectl dry-run validation."
fi

echo "Running strict schema validation..."
"$KUBECONFORM_BIN" -strict -summary -kubernetes-version "$KUBERNETES_VERSION" "$FULL_RENDER"

DEPLOYMENT_MANIFEST_PATH="$RENDER_DIR/deployment.yaml"
SERVICE_MANIFEST_PATH="$RENDER_DIR/service.yaml"
CRONJOB_MANIFEST_PATH="$RENDER_DIR/cronjob-dbbackup.yaml"
LEGACY_VALUES_PATH="$RENDER_DIR/legacy-values.yaml"
LEGACY_DEPLOYMENT_MANIFEST_PATH="$RENDER_DIR/legacy-deployment.yaml"
LEGACY_SERVICE_MANIFEST_PATH="$RENDER_DIR/legacy-service.yaml"

"$HELM_BIN" template nutrition-backend "$CHART_DIR" --show-only templates/deployment.yaml > "$DEPLOYMENT_MANIFEST_PATH"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" --show-only templates/service.yaml > "$SERVICE_MANIFEST_PATH"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" --show-only templates/cronjob-dbbackup.yaml > "$CRONJOB_MANIFEST_PATH"

cat <<'EOF' > "$LEGACY_VALUES_PATH"
service:
  port: 80
EOF

"$HELM_BIN" template nutrition-backend "$CHART_DIR" -f "$LEGACY_VALUES_PATH" --show-only templates/deployment.yaml > "$LEGACY_DEPLOYMENT_MANIFEST_PATH"
"$HELM_BIN" template nutrition-backend "$CHART_DIR" -f "$LEGACY_VALUES_PATH" --show-only templates/service.yaml > "$LEGACY_SERVICE_MANIFEST_PATH"

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if ! printf '%s\n' "$haystack" | grep -Fq -- "$needle"; then
    echo "Contract test failed: expected ${label}: ${needle}" >&2
    exit 1
  fi
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if printf '%s\n' "$haystack" | grep -Fq -- "$needle"; then
    echo "Contract test failed: unexpected ${label}: ${needle}" >&2
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
assert_contains "$(< "$DEPLOYMENT_MANIFEST_PATH")" "- ALL" "restricted capabilities in deployment"
assert_contains "$(< "$SERVICE_MANIFEST_PATH")" "targetPort: public" "service target to public listener"
assert_contains "$(< "$CRONJOB_MANIFEST_PATH")" "runAsNonRoot: true" "cronjob pod runs as non-root"
assert_contains "$(< "$CRONJOB_MANIFEST_PATH")" "allowPrivilegeEscalation: false" "cronjob container does not allow privilege escalation"
assert_contains "$(< "$CRONJOB_MANIFEST_PATH")" "- ALL" "cronjob container drops all capabilities"
assert_contains "$(< "$FULL_RENDER")" "containerPort: 8080" "rendered chart exposes public listener port"
assert_contains "$(< "$LEGACY_DEPLOYMENT_MANIFEST_PATH")" "name: public" "legacy values preserve public listener name"
assert_contains "$(< "$LEGACY_DEPLOYMENT_MANIFEST_PATH")" "containerPort: 8080" "legacy values default public listener port"
assert_contains "$(< "$LEGACY_DEPLOYMENT_MANIFEST_PATH")" "name: health" "legacy values preserve health listener name"
assert_contains "$(< "$LEGACY_DEPLOYMENT_MANIFEST_PATH")" "containerPort: 9000" "legacy values default health listener port"
assert_contains "$(< "$LEGACY_SERVICE_MANIFEST_PATH")" "targetPort: public" "legacy values default service target to public listener"
assert_not_contains "$(< "$FULL_RENDER")" "noNewPrivileges" "unsupported noNewPrivileges field"

echo "Chart contract tests passed."
