#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

require_command go

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
elif command -v py >/dev/null 2>&1; then
  PYTHON_BIN="py -3"
else
  echo "Python interpreter not found for beta capacity evidence validation." >&2
  exit 1
fi

raw_gates="${BETA_CAPACITY_GATES:-A B}"
read -r -a gates <<<"${raw_gates//,/ }"
if [[ ${#gates[@]} -eq 0 ]]; then
  echo "BETA_CAPACITY_GATES did not include any gates." >&2
  exit 1
fi

LOADGEN_BASE_URL="${LOADGEN_BASE_URL:-http://127.0.0.1:8000}"
if [[ "${BETA_CAPACITY_DRY_RUN:-false}" == "true" ]]; then
  default_output_dir="logs/loadgen-beta-dry-run"
  default_capacity_report_dir="logs/loadgen-beta-dry-run-capacity"
else
  default_output_dir="logs/loadgen"
  default_capacity_report_dir="docs/ops/capacity"
fi
LOADGEN_OUTPUT_DIR="${LOADGEN_OUTPUT_DIR:-${default_output_dir}}"
LOADGEN_CAPACITY_REPORT_DIR="${LOADGEN_CAPACITY_REPORT_DIR:-${default_capacity_report_dir}}"

for raw_gate in "${gates[@]}"; do
  gate="$(printf '%s' "${raw_gate}" | tr '[:lower:]' '[:upper:]')"
  [[ -n "${gate}" ]] || continue

  duration_var="BETA_GATE_${gate}_DURATION"
  duration="${!duration_var:-}"

  args=(
    --base-url "${LOADGEN_BASE_URL}"
    --gate "${gate}"
    --output-dir "${LOADGEN_OUTPUT_DIR}"
    --capacity-report-dir "${LOADGEN_CAPACITY_REPORT_DIR}"
  )

  if [[ -n "${duration}" ]]; then
    args+=(--duration "${duration}")
  fi
  if [[ -n "${ENGINE_CALLBACK_SECRET:-}" ]]; then
    args+=(--engine-callback-secret "${ENGINE_CALLBACK_SECRET}")
  fi
  if [[ "${BETA_CAPACITY_DRY_RUN:-false}" == "true" ]]; then
    args+=(--dry-run)
  fi

  log_section "Beta capacity Gate ${gate}"
  go run ./tools/loadgen "${args[@]}"
done

if [[ "${BETA_CAPACITY_DRY_RUN:-false}" == "true" ]]; then
  log_section "Skip beta capacity evidence validation"
  echo "Dry-run loadgen reports are command validation only and are not release evidence."
  exit 0
fi

log_section "Validate beta capacity evidence"
${PYTHON_BIN} "${SCRIPT_DIR}/check_beta_capacity_evidence.py" \
  --gates "${gates[@]}" \
  --capacity-report-dir "${LOADGEN_CAPACITY_REPORT_DIR}" \
  --raw-artifact-dir "${LOADGEN_OUTPUT_DIR}"
