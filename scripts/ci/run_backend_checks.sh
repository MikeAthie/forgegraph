#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

bash "${SCRIPT_DIR}/check_backend_runtime_writes.sh"
python "${SCRIPT_DIR}/check_run_state_machine.py"

cd "${ROOT}/backend"

require_uv
export_backend_ci_env
require_tcp_service "${DB_HOST}" "${DB_PORT}" "Postgres"
require_tcp_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

log_section "Backend format"
run_uv run ruff format --check .

log_section "Backend lint"
run_uv run ruff check .

log_section "Backend typecheck"
run_uv run mypy .

log_section "Backend tests"
run_uv run pytest
