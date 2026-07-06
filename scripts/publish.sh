#!/usr/bin/env bash
#
# Build and push the app image to a container registry.
#
# The Ugreen DXP2800 uses an Intel N100 (linux/amd64). When building on an Apple
# Silicon Mac, we must target linux/amd64 so the image runs on the NAS.
#
# Usage:
#   REGISTRY=docker.io/youruser/family-call-center TAG=v1.0.0 ./scripts/publish.sh
#   REGISTRY=ghcr.io/youruser/family-call-center   TAG=latest ./scripts/publish.sh
#
# Log in first:
#   docker login                                  # Docker Hub
#   echo "$GITHUB_TOKEN" | docker login ghcr.io -u USER --password-stdin
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REGISTRY="${REGISTRY:-ghcr.io/your-org/family-call-center}"
TAG="${TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"
IMAGE_REF="${REGISTRY}:${TAG}"

echo "Building ${IMAGE_REF} for ${PLATFORM}..."

# Prefer buildx for reliable cross-platform builds; fall back to classic build.
if docker buildx version >/dev/null 2>&1; then
  docker buildx build \
    --platform "${PLATFORM}" \
    --tag "${IMAGE_REF}" \
    --push \
    "${PROJECT_DIR}"
else
  echo "docker buildx not available; using classic build (must run on amd64)."
  docker build --platform "${PLATFORM}" -t "${IMAGE_REF}" "${PROJECT_DIR}"
  docker push "${IMAGE_REF}"
fi

echo ""
echo "Published ${IMAGE_REF}"
echo "On the NAS, set this in your environment or .env used by compose:"
echo "  IMAGE=${IMAGE_REF}"
