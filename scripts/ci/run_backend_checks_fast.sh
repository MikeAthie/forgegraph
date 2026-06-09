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
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=(python3)
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=(python)
elif command -v py >/dev/null 2>&1; then
  PYTHON_CMD=(py -3)
else
  echo "Python interpreter not found for backend fast checks." >&2
  exit 1
fi
"${PYTHON_CMD[@]}" "${SCRIPT_DIR}/check_run_state_machine.py"
"${PYTHON_CMD[@]}" "${SCRIPT_DIR}/check_projection_guardrails.py"

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
if [[ "${BACKEND_FAST_TYPECHECK:-0}" == "1" ]]; then
  run_uv run mypy .
else
  echo "Skipping mypy in backend-fast while the repo has known strict-mode baseline debt."
  echo "Set BACKEND_FAST_TYPECHECK=1 to exercise the full mypy gate locally or in a dedicated CI lane."
fi

log_section "Backend tests"
if [[ "${BACKEND_HIGH_RISK}" == "1" ]]; then
  echo "High-risk backend changes detected; running full pytest suite."
  run_uv run pytest
else
  run_uv run pytest --testmon
fi

log_section "Launch QA backend"
bash "${SCRIPT_DIR}/run_launch_qa_backend.sh"
