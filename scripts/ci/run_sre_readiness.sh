#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"

run_node() {
  if command -v node >/dev/null 2>&1; then
    node "$@"
    return
  fi
  if command -v node.exe >/dev/null 2>&1; then
    node.exe "$@"
    return
  fi
  if command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c node "$@"
    return
  fi
  echo "node is required for SRE dashboard tests" >&2
  return 127
}

cd "${ROOT}/backend"
require_uv
export_backend_ci_env
require_tcp_service "${DB_HOST}" "${DB_PORT}" "Postgres"
require_tcp_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

log_section "SRE readiness backend tests"
run_uv run pytest \
  tests/unit/services/test_sre_readiness.py \
  tests/integration/adapters/test_metrics_api.py \
  -q

cd "${ROOT}/frontend"
log_section "SRE readiness frontend tests"
run_node --max-old-space-size=4096 node_modules/jest/bin/jest.js --runInBand \
  __tests__/unit/pages/admin-operations.test.tsx
