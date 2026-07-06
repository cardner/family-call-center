#!/usr/bin/env bash
#
# Deploy on the NAS: materialize secrets from 1Password (if available), then pull
# the published image and (re)start the stack. Run from the deploy folder that
# contains docker-compose.yml and .env.op.template.
#
# Alternative that avoids writing .env to disk (requires op on the NAS):
#   op run --env-file=.env.op.template -- docker compose pull && docker compose up -d
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but was not found in PATH." >&2
  exit 1
fi

if command -v op >/dev/null 2>&1; then
  echo "Injecting secrets from 1Password into .env..."
  op inject -i .env.op.template -o .env --force
  chmod 600 .env
else
  echo "1Password CLI (op) not found; expecting an existing .env file."
  if [[ ! -f .env ]]; then
    echo "Missing .env and no op CLI to generate it. Aborting." >&2
    exit 1
  fi
fi

echo "Pulling latest image and starting the stack..."
docker compose pull
docker compose up -d

echo ""
BASE_URL="$(grep -E '^BASE_URL=' .env | head -n 1 | cut -d '=' -f 2- | sed 's:/*$::' || true)"
echo "Deploy complete."
if [[ -n "${BASE_URL:-}" ]]; then
  echo "Health check: ${BASE_URL}/health"
else
  echo "Health check: <set BASE_URL in .env>/health"
fi
