#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

log_section "Engine canonical event envelope guardrails"

if grep -RInE 'CloudEvent|specversion|datacontenttype|toCloudEventEnvelope' engine \
  --include='*.go' \
  --exclude='*_test.go' >/tmp/forgegraph_engine_cloudevent_hits.txt 2>/dev/null; then
  echo "Engine legacy CloudEvent callback emission detected. Engine callbacks must use canonical envelope v2 only." >&2
  cat /tmp/forgegraph_engine_cloudevent_hits.txt >&2
  exit 1
fi
