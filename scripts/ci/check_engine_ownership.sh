#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

require_command rg

log_section "Engine ownership guardrails"

if rg -n 'legacy-db|legacy_db|run_repository_fallback' engine; then
  echo "Legacy engine persistence fallback detected. Remove forbidden runtime compatibility paths." >&2
  exit 1
fi

if rg -n 'normalizeRunStateMode\\(\"postgres\"\\).*dual-write' engine/main_test.go; then
  echo "Legacy postgres alias expectation detected in engine tests." >&2
  exit 1
fi

rg -n 'ENGINE_ALLOW_IN_MEMORY_MODE' engine/main.go >/dev/null || {
  echo "Missing ENGINE_ALLOW_IN_MEMORY_MODE safeguard in engine startup." >&2
  exit 1
}

rg -n 'control-plane-http' engine/main.go >/dev/null || {
  echo "Missing explicit control-plane-http enforcement in engine startup." >&2
  exit 1
}
