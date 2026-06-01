#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

bash "${SCRIPT_DIR}/check_live_playwright_no_mocks.sh"

cd "${ROOT}/frontend"
require_command npx

export PLAYWRIGHT_RUNTIME_TARGET="${PLAYWRIGHT_RUNTIME_TARGET:-local}"
export PLAYWRIGHT_WORKERS="${PLAYWRIGHT_WORKERS:-1}"
export PLAYWRIGHT_BACKEND_PORT="${PLAYWRIGHT_BACKEND_PORT:-8002}"
export PLAYWRIGHT_DEV_PORT="${PLAYWRIGHT_DEV_PORT:-3001}"
export PLAYWRIGHT_API_URL="${PLAYWRIGHT_API_URL:-http://127.0.0.1:${PLAYWRIGHT_BACKEND_PORT}}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-${PLAYWRIGHT_API_URL}}"
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-5433}"
export DB_USER="${DB_USER:-forgegraph}"
export DB_PASSWORD="${DB_PASSWORD:-forgegraph_secret}"
export USE_IN_MEMORY_CHANNEL_LAYER="${USE_IN_MEMORY_CHANNEL_LAYER:-false}"
export USE_IN_MEMORY_CACHE="${USE_IN_MEMORY_CACHE:-false}"
export PLAYWRIGHT_LOAD_SMOKE_RUNS="${PLAYWRIGHT_LOAD_SMOKE_RUNS:-100}"
export PLAYWRIGHT_LOAD_SMOKE_START_CONCURRENCY="${PLAYWRIGHT_LOAD_SMOKE_START_CONCURRENCY:-5}"
export PLAYWRIGHT_LOAD_SMOKE_TIMEOUT_MS="${PLAYWRIGHT_LOAD_SMOKE_TIMEOUT_MS:-840000}"
export PLAYWRIGHT_LOAD_SMOKE_TERMINAL_TIMEOUT_MS="${PLAYWRIGHT_LOAD_SMOKE_TERMINAL_TIMEOUT_MS:-720000}"
export PLAYWRIGHT_WEB_SERVER_TIMEOUT_MS="${PLAYWRIGHT_WEB_SERVER_TIMEOUT_MS:-180000}"
export PLAYWRIGHT_LIVE_AUTH_TIMEOUT_MS="${PLAYWRIGHT_LIVE_AUTH_TIMEOUT_MS:-60000}"
export PLAYWRIGHT_API_REQUEST_TIMEOUT_MS="${PLAYWRIGHT_API_REQUEST_TIMEOUT_MS:-60000}"
export PLAYWRIGHT_ENGINE_START_RETRY_MS="${PLAYWRIGHT_ENGINE_START_RETRY_MS:-60000}"
export PLAYWRIGHT_ENGINE_HOST="${PLAYWRIGHT_ENGINE_HOST:-127.0.0.1}"
export PLAYWRIGHT_ENGINE_PORT="${PLAYWRIGHT_ENGINE_PORT:-50071}"
export PLAYWRIGHT_ENGINE_TARGETS="${PLAYWRIGHT_ENGINE_TARGETS:-playwright-engine-1=${PLAYWRIGHT_ENGINE_HOST}:${PLAYWRIGHT_ENGINE_PORT}}"
export PLAYWRIGHT_RUN_QUEUE_SLEEP_SECONDS="${PLAYWRIGHT_RUN_QUEUE_SLEEP_SECONDS:-1}"
export ENGINE_RUNTIME_INTENT_OUTCOME_TIMEOUT_MS="${ENGINE_RUNTIME_INTENT_OUTCOME_TIMEOUT_MS:-30000}"
export PLAYWRIGHT_LLM_MOCK_ERROR_MODE="${PLAYWRIGHT_LLM_MOCK_ERROR_MODE:-off}"
export AUTH_REGISTER_THROTTLE_RATE="${AUTH_REGISTER_THROTTLE_RATE:-10000/min}"
export AUTH_LOGIN_THROTTLE_RATE="${AUTH_LOGIN_THROTTLE_RATE:-10000/min}"
export AUTH_REFRESH_THROTTLE_RATE="${AUTH_REFRESH_THROTTLE_RATE:-10000/min}"
export AUTH_WS_TICKET_THROTTLE_RATE="${AUTH_WS_TICKET_THROTTLE_RATE:-10000/min}"
export API_ANON_THROTTLE_RATE="${API_ANON_THROTTLE_RATE:-10000/min}"
export API_USER_THROTTLE_RATE="${API_USER_THROTTLE_RATE:-10000/min}"
export RUN_START_RATE_LIMIT_PER_MIN="${RUN_START_RATE_LIMIT_PER_MIN:-10000}"
export RUN_INVOKE_RATE_LIMIT_PER_MIN="${RUN_INVOKE_RATE_LIMIT_PER_MIN:-10000}"
export RUN_MAX_ACTIVE_PER_TENANT="${RUN_MAX_ACTIVE_PER_TENANT:-250}"
export RUN_QUEUE_ENABLED="${RUN_QUEUE_ENABLED:-true}"
export RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT="${RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT:-10}"
export RUN_QUEUE_RETRY_DELAY_SECONDS="${RUN_QUEUE_RETRY_DELAY_SECONDS:-1}"

LOAD_SMOKE_OWNS_DB=false
if [[ -z "${DB_NAME:-}" && "${PLAYWRIGHT_RUNTIME_TARGET}" == "local" ]]; then
  export DB_NAME="forgegraph_load_smoke_$(date +%s)_$$"
  LOAD_SMOKE_OWNS_DB=true
fi
export DB_NAME="${DB_NAME:-forgegraph}"

create_load_smoke_database() {
  (cd "${ROOT}/backend" && run_uv run python - <<'PY')
import os

import psycopg2
from psycopg2 import sql

db_name = os.environ["DB_NAME"]
connection = psycopg2.connect(
    dbname="postgres",
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
)
connection.autocommit = True
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
finally:
    connection.close()
PY
}

drop_load_smoke_database() {
  (cd "${ROOT}/backend" && run_uv run python - <<'PY')
import os

import psycopg2
from psycopg2 import sql

db_name = os.environ["DB_NAME"]
connection = psycopg2.connect(
    dbname="postgres",
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
)
connection.autocommit = True
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (db_name,),
        )
        cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))
finally:
    connection.close()
PY
}

cleanup() {
  if [[ "${LOAD_SMOKE_OWNS_DB}" == "true" ]]; then
    drop_load_smoke_database || true
  fi
}
trap cleanup EXIT

if [[ "${LOAD_SMOKE_OWNS_DB}" == "true" ]]; then
  log_section "Create isolated load-smoke database"
  create_load_smoke_database
fi

if [[ "${ROOT}" == /mnt/* ]] && command -v cmd.exe >/dev/null 2>&1; then
  wsl_env_names=(
    PLAYWRIGHT_RUNTIME_TARGET
    PLAYWRIGHT_WORKERS
    PLAYWRIGHT_BACKEND_PORT
    PLAYWRIGHT_DEV_PORT
    PLAYWRIGHT_API_URL
    NEXT_PUBLIC_API_URL
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    USE_IN_MEMORY_CHANNEL_LAYER
    USE_IN_MEMORY_CACHE
    PLAYWRIGHT_LOAD_SMOKE_RUNS
    PLAYWRIGHT_LOAD_SMOKE_START_CONCURRENCY
    PLAYWRIGHT_LOAD_SMOKE_TIMEOUT_MS
    PLAYWRIGHT_LOAD_SMOKE_TERMINAL_TIMEOUT_MS
    PLAYWRIGHT_WEB_SERVER_TIMEOUT_MS
    PLAYWRIGHT_LIVE_AUTH_TIMEOUT_MS
    PLAYWRIGHT_API_REQUEST_TIMEOUT_MS
    PLAYWRIGHT_ENGINE_START_RETRY_MS
    PLAYWRIGHT_ENGINE_HOST
    PLAYWRIGHT_ENGINE_PORT
    PLAYWRIGHT_ENGINE_TARGETS
    PLAYWRIGHT_RUN_QUEUE_SLEEP_SECONDS
    ENGINE_RUNTIME_INTENT_OUTCOME_TIMEOUT_MS
    PLAYWRIGHT_LLM_MOCK_ERROR_MODE
    AUTH_REGISTER_THROTTLE_RATE
    AUTH_LOGIN_THROTTLE_RATE
    AUTH_REFRESH_THROTTLE_RATE
    AUTH_WS_TICKET_THROTTLE_RATE
    API_ANON_THROTTLE_RATE
    API_USER_THROTTLE_RATE
    RUN_START_RATE_LIMIT_PER_MIN
    RUN_INVOKE_RATE_LIMIT_PER_MIN
    RUN_MAX_ACTIVE_PER_TENANT
    RUN_QUEUE_ENABLED
    RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT
    RUN_QUEUE_RETRY_DELAY_SECONDS
  )
  IFS=:
  export WSLENV="${wsl_env_names[*]}${WSLENV:+:${WSLENV}}"
  unset IFS
fi

run_npx() {
  if [[ "${ROOT}" == /mnt/* ]] && command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c npx "$@"
    return
  fi
  npx "$@"
}

log_section "100-run queued no-LLM load smoke"
run_npx playwright test __tests__/e2e/load-smoke-live.spec.ts --project=chromium
