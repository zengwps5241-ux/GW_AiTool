#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BASE_IMAGE="${BASE_IMAGE:-gokagent-backend:base}"
IMAGE="${IMAGE:-gokagent-backend:release}"

docker build \
  -f "${ROOT_DIR}/docker/Dockerfile_base" \
  -t "${BASE_IMAGE}" \
  "${ROOT_DIR}"

docker build \
  --build-arg "BACKEND_BASE_IMAGE=${BASE_IMAGE}" \
  -f "${ROOT_DIR}/docker/Dockerfile.release" \
  -t "${IMAGE}" \
  "${ROOT_DIR}"

if [[ -n "${RELEASE_TAR:-}" ]]; then
  docker save "${IMAGE}" -o "${RELEASE_TAR}"
fi
