#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/engine"

require_command go

log_section "Engine architecture ownership guard"
bash "${SCRIPT_DIR}/check_engine_ownership.sh"
bash "${SCRIPT_DIR}/check_engine_event_envelope.sh"

log_section "Engine deterministic and architecture tests"
go test . -count=1
go test ./application/usecase -run "Architecture|Deterministic|RuntimeIntent|FailsClosed|Resume|Retry" -count=1
