#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
HEALTH_URL="http://localhost:8080/health"
FUNNEL_TARGET="localhost:8080"
APP_LOG="$PROJECT_DIR/logs/manual-run.log"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name"
    exit 1
  fi
}

is_healthy() {
  curl -fsS "$HEALTH_URL" >/dev/null 2>&1
}

start_app_if_needed() {
  if is_healthy; then
    echo "App already healthy on port 8080."
    return
  fi

  echo "Starting app with $PYTHON_BIN ..."
  mkdir -p "$PROJECT_DIR/logs"
  nohup "$PYTHON_BIN" "$PROJECT_DIR/run.py" >> "$APP_LOG" 2>&1 &

  local attempt=0
  local max_attempts=20
  while [[ $attempt -lt $max_attempts ]]; do
    if is_healthy; then
      echo "App is healthy on port 8080."
      return
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  echo "App did not become healthy. Last log lines:"
  tail -n 40 "$APP_LOG" || true
  exit 1
}

configure_funnel() {
  echo "Configuring Tailscale Funnel -> $FUNNEL_TARGET ..."
  tailscale funnel --bg "$FUNNEL_TARGET"
  if ! tailscale funnel status | grep -q "proxy http://$FUNNEL_TARGET"; then
    echo "Funnel was not configured as expected."
    tailscale funnel status
    exit 1
  fi
}

main() {
  require_command curl
  require_command tailscale

  if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "Missing .env at $PROJECT_DIR/.env"
    exit 1
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Missing Python virtualenv binary at $PYTHON_BIN"
    exit 1
  fi

  local base_url
  base_url="$(grep '^BASE_URL=' "$PROJECT_DIR/.env" | head -n 1 | cut -d '=' -f 2- | sed 's:/*$::')"

  start_app_if_needed
  configure_funnel

  echo ""
  echo "Recovery complete."
  echo "Local health: $HEALTH_URL"
  if [[ -n "$base_url" ]]; then
    echo "Public health: $base_url/health"
  else
    echo "Public health: <set BASE_URL in .env>/health"
  fi
}

main "$@"
