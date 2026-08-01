#!/bin/sh

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-nutrition-backend-contract-test}"
IMAGE_TAG="${IMAGE_TAG:-ci}"
IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
DOCKERFILE_PATH="${SCRIPT_DIR}/../Dockerfile"
SKIP_IMAGE_BUILD="${SKIP_IMAGE_BUILD:-0}"
PRESERVE_IMAGE="${PRESERVE_IMAGE:-0}"

if [ "$SKIP_IMAGE_BUILD" = "1" ]; then
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Contract image ${IMAGE} is not available and SKIP_IMAGE_BUILD is enabled." >&2
    exit 1
  fi
else
  docker build -f "$DOCKERFILE_PATH" -t "$IMAGE" "$PROJECT_ROOT"
fi

if [ "$PRESERVE_IMAGE" != "1" ]; then
  trap 'docker image rm -f "$IMAGE" >/dev/null 2>&1 || true' EXIT
fi

if grep -q "NOPASSWD:ALL" "$DOCKERFILE_PATH"; then
  echo "Dockerfile still defines passwordless sudo" >&2
  exit 1
fi

if ! grep -E "^EXPOSE[[:space:]]+8080[[:space:]]+9000" "$DOCKERFILE_PATH" >/dev/null 2>&1; then
  echo "Dockerfile does not expose required backend listeners 8080 and 9000" >&2
  exit 1
fi

if grep -Eq "\\bsudo\\b" "$DOCKERFILE_PATH"; then
  echo "Dockerfile still installs or references sudo" >&2
  exit 1
fi

RUNTIME_CHECK="$(
  docker run --rm --entrypoint /bin/sh "$IMAGE" -lc '
    set -eu

    if [ "$(id -u)" -eq 0 ]; then
      echo "runtime user is root" >&2
      exit 1
    fi

    if grep -Rqs "NOPASSWD:ALL" /etc/sudoers /etc/sudoers.d 2>/dev/null; then
      echo "runtime image contains NOPASSWD sudo policy" >&2
      exit 1
    fi

    if command -v sudo >/dev/null 2>&1; then
      if sudo -n true >/dev/null 2>&1; then
        echo "runtime image can escalate privileges without password" >&2
        exit 1
      fi
    fi

    echo "runtime_uid=$(id -u)"
  '
)"

if ! echo "$RUNTIME_CHECK" | grep -q "runtime_uid="; then
  echo "Runtime container contract check failed" >&2
  exit 1
fi

echo "$RUNTIME_CHECK"
echo "Backend image contract tests passed."
