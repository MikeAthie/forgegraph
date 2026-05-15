#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/backend"

require_uv
export_backend_ci_env
require_tcp_service "${DB_HOST}" "${DB_PORT}" "Postgres"
require_tcp_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

log_section "Launch QA backend"
run_uv run pytest \
  tests/integration/adapters/runs \
  tests/integration/adapters/test_run_history_security_api.py \
  tests/integration/adapters/test_credentials_security_api.py \
  tests/integration/adapters/test_audit_logs_api.py \
  tests/integration/adapters/test_metrics_api.py \
  tests/unit/services/test_redaction.py \
  -q
