#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
elif command -v py >/dev/null 2>&1; then
  PYTHON_BIN="py -3"
else
  echo "Python interpreter not found for governance checks." >&2
  exit 1
fi

log_section "Governance guardrails"
${PYTHON_BIN} "${SCRIPT_DIR}/check_architecture_signoff.py"
${PYTHON_BIN} "${SCRIPT_DIR}/check_launch_claims.py"
${PYTHON_BIN} "${SCRIPT_DIR}/check_frontend_accounting_metrics.py"
${PYTHON_BIN} "${SCRIPT_DIR}/check_idempotency_guardrails.py"
${PYTHON_BIN} "${SCRIPT_DIR}/check_remediation_roadmap.py"
