#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/engine"

require_command go

log_section "Engine gofmt"
unformatted="$(gofmt -l .)"
if [ -n "${unformatted}" ]; then
  echo "gofmt required on:" >&2
  echo "${unformatted}" >&2
  exit 1
fi

bash "${ROOT}/scripts/check_engine_statelessness.sh"
run_python "${SCRIPT_DIR}/check_engine_no_release_sleeps.py"
bash "${SCRIPT_DIR}/check_engine_ownership.sh"
bash "${SCRIPT_DIR}/check_engine_event_envelope.sh"

log_section "Engine vet"
go vet ./...

log_section "Engine tests"
go test ./...

log_section "Engine race tests"
run_go_race_or_skip ./...
