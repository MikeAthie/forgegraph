#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/engine"

require_command go

bash "${ROOT}/scripts/check_engine_statelessness.sh"
run_python "${SCRIPT_DIR}/check_engine_no_release_sleeps.py"

log_section "Engine integration tests"
go test ./adapter/... ./test/... ./tests/e2e/... -count=1
