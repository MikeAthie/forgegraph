#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || pwd)"

bash "${SCRIPT_DIR}/run_backend_unit.sh"
bash "${SCRIPT_DIR}/run_backend_integration.sh"
bash "${SCRIPT_DIR}/run_backend_migration.sh"
bash "${SCRIPT_DIR}/run_security_regression.sh"
bash "${SCRIPT_DIR}/run_sre_readiness.sh"

bash "${SCRIPT_DIR}/run_engine_deterministic.sh"
bash "${SCRIPT_DIR}/run_engine_integration.sh"
bash "${SCRIPT_DIR}/run_engine_race.sh"

bash "${SCRIPT_DIR}/run_frontend_unit.sh"
bash "${SCRIPT_DIR}/run_frontend_playwright_mocked.sh"

bash "${SCRIPT_DIR}/run_launch_qa_backend.sh"
bash "${SCRIPT_DIR}/run_launch_qa_engine.sh"
bash "${SCRIPT_DIR}/run_launch_qa_frontend.sh"

bash "${SCRIPT_DIR}/check_live_playwright_no_mocks.sh"

cd "${ROOT}/frontend"
export PLAYWRIGHT_RUNTIME_TARGET="${PLAYWRIGHT_RUNTIME_TARGET:-local}"
export PLAYWRIGHT_WORKERS="${PLAYWRIGHT_WORKERS:-1}"
export USE_IN_MEMORY_CHANNEL_LAYER="${USE_IN_MEMORY_CHANNEL_LAYER:-false}"
export USE_IN_MEMORY_CACHE="${USE_IN_MEMORY_CACHE:-false}"
export USE_SQLITE="${USE_SQLITE:-false}"

npx playwright test \
  __tests__/e2e/human-gate-live.spec.ts \
  __tests__/e2e/production-launch-live.spec.ts \
  __tests__/e2e/operator-recovery-live.spec.ts \
  __tests__/e2e/tenant-isolation-live.spec.ts \
  --project=chromium

npx playwright test \
  __tests__/e2e/production-launch-live.spec.ts \
  __tests__/e2e/operator-recovery-live.spec.ts \
  --project=chromium

npx playwright test __tests__/e2e/human-gate-live.spec.ts --project=chromium
npx playwright test __tests__/e2e/failure-retry-dead-letter-live.spec.ts --project=chromium
npx playwright test __tests__/e2e/tenant-isolation-live.spec.ts --project=chromium

cd "${ROOT}"
bash "${SCRIPT_DIR}/run_load_smoke.sh"

if [[ "${RUN_REQUIRED_CHECKS_INCLUDE_DOCKER_SMOKE:-true}" == "true" ]]; then
  bash "${SCRIPT_DIR}/run_docker_full_stack_smoke.sh"
fi
