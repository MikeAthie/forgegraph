#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/engine"

require_command go

log_section "Launch QA engine"
go test ./application/usecase -run "Scheduler|OnError|RetryAfter|NonRetryable" -count=1
go test ./adapter/executor -run "HTTPExecutor|ToolExecutor|PromptExecutor" -count=1
CGO_ENABLED=1 go test -race ./application/usecase ./adapter/executor -count=1

