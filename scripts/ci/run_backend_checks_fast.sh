#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

bash "${SCRIPT_DIR}/detect_changed_scopes.sh" "${TMP_DIR}"
# shellcheck source=/dev/null
source "${TMP_DIR}/scopes.env"

if [[ "${BACKEND_CHANGED}" != "1" ]]; then
  log_section "Backend fast checks"
  echo "No backend changes detected; skipping."
  exit 0
fi

bash "${SCRIPT_DIR}/check_backend_runtime_writes.sh"

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
if [[ "${BACKEND_HIGH_RISK}" == "1" ]]; then
  echo "High-risk backend changes detected; running full pytest suite."
  run_uv run pytest
else
  run_uv run pytest --testmon
fi

log_section "Launch QA backend"
bash "${SCRIPT_DIR}/run_launch_qa_backend.sh"
