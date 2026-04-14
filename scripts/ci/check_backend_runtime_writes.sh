#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

log_section "Backend runtime write guardrails"

if command -v python3 >/dev/null 2>&1; then
  python3 "${SCRIPT_DIR}/check_backend_runtime_writes.py"
elif command -v python >/dev/null 2>&1; then
  python "${SCRIPT_DIR}/check_backend_runtime_writes.py"
elif command -v py >/dev/null 2>&1; then
  py -3 "${SCRIPT_DIR}/check_backend_runtime_writes.py"
else
  echo "Python interpreter not found for backend runtime write guardrails." >&2
  exit 1
fi
