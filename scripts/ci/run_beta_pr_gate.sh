#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

log_section "Beta PR governance and launch guardrails"
bash "${SCRIPT_DIR}/run_governance_checks.sh"

log_section "Beta PR backend P0 fast slice"
bash "${SCRIPT_DIR}/run_backend_checks_fast.sh"

log_section "Beta PR engine P0 fast slice"
bash "${SCRIPT_DIR}/run_engine_checks_fast.sh"

log_section "Beta PR frontend P0 fast slice"
bash "${SCRIPT_DIR}/run_frontend_checks_fast.sh"

log_section "Beta PR live no-mock guard"
bash "${SCRIPT_DIR}/check_live_playwright_no_mocks.sh"

log_section "Beta PR loadgen regression smoke"
bash "${SCRIPT_DIR}/run_loadgen_smoke.sh"
