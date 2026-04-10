#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

bash "${SCRIPT_DIR}/detect_changed_scopes.sh" "${TMP_DIR}"
# shellcheck source=/dev/null
source "${TMP_DIR}/scopes.env"

if [[ "${FRONTEND_CHANGED}" != "1" ]]; then
  log_section "Frontend fast checks"
  echo "No frontend changes detected; skipping."
  exit 0
fi

cd "${ROOT}/frontend"

require_command npm
require_command npx

export JEST_CACHE_DIR="${ROOT}/frontend/.jest-cache"

log_section "Frontend format"
npm run format:check

log_section "Frontend lint"
npm run lint

mapfile -t related_files < <(
  grep -E '^frontend/.*\.(js|jsx|ts|tsx)$' "${TMP_DIR}/frontend_files.txt" \
    | sed 's#^frontend/##' \
    || true
)

log_section "Frontend unit tests"
if [[ "${FRONTEND_HIGH_RISK}" == "1" ]]; then
  echo "High-risk frontend changes detected; running full Jest suite."
  npm test
elif [[ ${#related_files[@]} -gt 0 ]]; then
  npm run test:related -- --passWithNoTests "${related_files[@]}"
else
  echo "No related JS/TS frontend files detected; skipping Jest selection."
fi

log_section "Frontend build"
if [[ "${FRONTEND_BUILD_REQUIRED}" == "1" ]]; then
  npm run build
else
  echo "No source/config frontend changes detected; skipping build."
fi

log_section "Launch QA frontend"
bash "${SCRIPT_DIR}/run_launch_qa_frontend.sh"
