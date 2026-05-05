#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

BAD_PATTERNS=(
  "RedisMemoryStore"
  "SaveSummary"
  "SaveFact"
  "PersistMemory"
  "MemoryUsage"
  "summarization_worker"
)

ALLOWLIST="scripts/engine_statelessness_allowlist.txt"

if [ ! -f "${ALLOWLIST}" ]; then
  echo "Missing engine statelessness allowlist: ${ALLOWLIST}" >&2
  exit 1
fi

is_allowed() {
  local pattern="$1"
  local path="$2"
  awk -F'\t' -v pattern="${pattern}" -v path="${path}" '
    $0 ~ /^[[:space:]]*($|#)/ { next }
    $1 == pattern && $2 == path { found = 1 }
    END { exit(found ? 0 : 1) }
  ' "${ALLOWLIST}"
}

violations=0
for pattern in "${BAD_PATTERNS[@]}"; do
  while IFS=: read -r path line text; do
    [ -n "${path}" ] || continue
    if ! is_allowed "${pattern}" "${path}"; then
      printf '%s:%s:%s\n' "${path}" "${line}" "${text}" >&2
      echo "Engine statelessness violation: ${pattern}" >&2
      violations=1
    fi
  done < <(
    if command -v rg >/dev/null 2>&1; then
      rg -n \
        --hidden \
        --glob '!**/.git/**' \
        --glob '!engine/engine.exe' \
        --glob '!engine/testsprite_tests/tmp/**' \
        --glob '!testsprite_tests/tmp/**' \
        --glob '!**/testsprite_tests/tmp/**' \
        "${pattern}" engine || true
    else
      find engine \
        \( -path '*/.git/*' -o -path 'engine/testsprite_tests/tmp/*' -o -name engine.exe \) \
        -prune -o -type f -print0 \
        | xargs -0 grep -n -I "${pattern}" 2>/dev/null || true
    fi
  )
done

exit "${violations}"
