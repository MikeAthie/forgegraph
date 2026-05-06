#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

log_section "Beta release local production evidence"
LOCAL_GATE_INCLUDE_DOCKER_SMOKE=false \
  LOCAL_GATE_DOWN_ON_EXIT="${LOCAL_GATE_DOWN_ON_EXIT:-false}" \
  bash "${SCRIPT_DIR}/run_local_production_evidence.sh"

if [[ "${BETA_RELEASE_RUN_CAPACITY_GATES:-true}" == "true" ]]; then
  log_section "Beta release Gate A/B capacity evidence"
  BETA_CAPACITY_GATES="${BETA_CAPACITY_GATES:-A B}" \
    bash "${SCRIPT_DIR}/run_beta_capacity_gates.sh"
else
  echo "Skipping Gate A/B capacity evidence because BETA_RELEASE_RUN_CAPACITY_GATES=false."
fi

if [[ "${BETA_RELEASE_INCLUDE_DOCKER_SMOKE:-true}" == "true" ]]; then
  log_section "Beta release Docker image smoke"
  bash "${SCRIPT_DIR}/run_docker_full_stack_smoke.sh"
else
  echo "Skipping Docker image smoke because BETA_RELEASE_INCLUDE_DOCKER_SMOKE=false."
fi

log_section "Beta release manual walkthrough"
cat <<'EOF'
Record the operator walkthrough decision before release:
- Why is this company stuck?
- What did this cost, learn, and decide?

The release remains blocked unless the walkthrough is approved without raw-log
dependency and the state ownership ADR has human signoff.
EOF
