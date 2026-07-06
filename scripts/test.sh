#!/usr/bin/env bash
#
# Run the automated test suite.
#
#   ./scripts/test.sh            # run all tests
#   ./scripts/test.sh -k admin   # pass extra args through to pytest
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

exec python -m pytest -v "$@"
