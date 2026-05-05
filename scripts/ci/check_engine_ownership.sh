#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

search_text() {
  local pattern="$1"
  shift

  if command -v rg >/dev/null 2>&1; then
    rg -n "${pattern}" "$@"
  else
    grep -R -n -E "${pattern}" "$@"
  fi
}

search_file() {
  local pattern="$1"
  local file="$2"

  if command -v rg >/dev/null 2>&1; then
    rg -n "${pattern}" "${file}"
  else
    grep -n -E "${pattern}" "${file}"
  fi
}

log_section "Engine ownership guardrails"

[ -f docs/architecture/runtime-invariants.md ] || {
  echo "Missing canonical runtime contract: docs/architecture/runtime-invariants.md" >&2
  exit 1
}

if search_text 'legacy-db|legacy_db|run_repository_fallback' engine; then
  echo "Legacy engine persistence fallback detected. Remove forbidden runtime compatibility paths." >&2
  exit 1
fi

if command -v rg >/dev/null 2>&1; then
  if rg -n '"database/sql"|gorm\.io|github\.com/lib/pq|github\.com/jackc/pgx|github\.com/jmoiron/sqlx' engine --glob '*.go' --glob '!architecture_enforcement_test.go'; then
    echo "Direct database persistence import detected in engine Go source." >&2
    exit 1
  fi
else
  if grep -R -n -E --include='*.go' --exclude='architecture_enforcement_test.go' '"database/sql"|gorm\.io|github\.com/lib/pq|github\.com/jackc/pgx|github\.com/jmoiron/sqlx' engine; then
    echo "Direct database persistence import detected in engine Go source." >&2
    exit 1
  fi
fi

if search_file 'normalizeRunStateMode\("postgres"\).*dual-write' engine/main_test.go; then
  echo "Legacy postgres alias expectation detected in engine tests." >&2
  exit 1
fi

search_file 'ENGINE_ALLOW_IN_MEMORY_MODE' engine/main.go >/dev/null || {
  echo "Missing ENGINE_ALLOW_IN_MEMORY_MODE safeguard in engine startup." >&2
  exit 1
}

search_file 'control-plane-http' engine/main.go >/dev/null || {
  echo "Missing explicit control-plane-http enforcement in engine startup." >&2
  exit 1
}

durable_memory_pattern='RedisMemoryStore|NewRedisMemoryStore|StoreSummary\(|StoreFacts\(|keyPatternMemory'

if command -v rg >/dev/null 2>&1; then
  mapfile -t durable_memory_matches < <(
    rg -l "${durable_memory_pattern}" engine --glob '*.go' --glob '!architecture_enforcement_test.go' --glob '!statelessness_guard_test.go' | sort
  )
else
  mapfile -t durable_memory_matches < <(
    grep -R -l -E --include='*.go' --exclude='architecture_enforcement_test.go' --exclude='statelessness_guard_test.go' "${durable_memory_pattern}" engine | sort
  )
fi

if [ "${#durable_memory_matches[@]}" -gt 0 ]; then
  printf '%s\n' "${durable_memory_matches[@]}" >&2
  echo "Engine durable product-memory persistence detected. Engine summaries/facts must move through backend-owned memory intents only." >&2
  exit 1
fi

if [ -f scripts/ci/engine_durable_memory_temporary_violations.tsv ]; then
  echo "Temporary engine durable memory exception manifest must not be reintroduced." >&2
  exit 1
fi
