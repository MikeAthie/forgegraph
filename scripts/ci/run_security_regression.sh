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
  echo "node is required for frontend security boundary tests" >&2
  return 127
}

cd "${ROOT}/backend"

require_uv
export_backend_ci_env
require_tcp_service "${DB_HOST}" "${DB_PORT}" "Postgres"
require_tcp_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

log_section "Security regression tests"
run_uv run pytest \
  tests/integration/adapters/test_security_matrix.py \
  tests/integration/adapters/test_run_history_security_api.py \
  tests/integration/adapters/test_credentials_security_api.py \
  tests/integration/adapters/test_audit_logs_api.py \
  tests/integration/adapters/test_engine_api.py \
  tests/integration/adapters/test_architecture_enforcement.py::test_operator_access_remains_org_scoped \
  -q

cd "${ROOT}/frontend"
log_section "Frontend security boundary tests"
run_node --max-old-space-size=4096 node_modules/jest/bin/jest.js --runInBand \
  __tests__/unit/security-boundaries.test.tsx \
  __tests__/unit/pages/approvals-architecture.test.tsx

cd "${ROOT}/engine"
log_section "Engine signing and secret redaction tests"
go test ./adapter/gateway -timeout 120s
