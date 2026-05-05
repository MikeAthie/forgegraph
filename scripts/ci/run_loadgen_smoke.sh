#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

require_command go

log_section "Loadgen unit tests"
go test ./tools/loadgen/...

log_section "Loadgen dry-run smoke"
go run ./tools/loadgen \
  --dry-run \
  --tenants 2 \
  --agents 4 \
  --runs-per-tenant 2 \
  --ws-clients 4 \
  --duration 2m \
  --with-memory \
  --with-accounting \
  --output-dir logs/loadgen-smoke

if [[ "${FORGEGRAPH_RUN_LIVE_LOADGEN_SMOKE:-false}" == "true" ]]; then
  log_section "Loadgen live smoke"
  go run ./tools/loadgen \
    --base-url "${LOADGEN_BASE_URL:-http://127.0.0.1:8000}" \
    --engine-callback-secret "${ENGINE_CALLBACK_SECRET:-}" \
    --tenants 2 \
    --agents 4 \
    --runs-per-tenant 2 \
    --ws-clients 4 \
    --duration "${LOADGEN_SMOKE_DURATION:-2m}" \
    --with-memory \
    --with-accounting \
    --output-dir logs/loadgen-smoke-live
fi
