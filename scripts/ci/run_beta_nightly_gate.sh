#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

log_section "Beta nightly required checks"
bash "${SCRIPT_DIR}/run_required_checks.sh"

log_section "Beta nightly runtime transport chaos"
cd "${ROOT}/backend"
require_uv
export_backend_ci_env
require_tcp_service "${DB_HOST}" "${DB_PORT}" "Postgres"
require_tcp_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"
run_uv run pytest tests/e2e/test_redis_runtime_transport_failures.py -q
