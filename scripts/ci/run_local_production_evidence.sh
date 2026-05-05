#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

require_command docker

export DB_NAME="${DB_NAME:-forgegraph}"
export DB_USER="${DB_USER:-forgegraph}"
export DB_PASSWORD="${DB_PASSWORD:-forgegraph_secret}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-forgegraph}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5433}"
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_ADDR="${REDIS_ADDR:-${REDIS_HOST}:${REDIS_PORT}}"
export SECRET_KEY="${SECRET_KEY:-local-production-evidence-not-a-secret}"
export DEBUG="${DEBUG:-False}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-localhost,127.0.0.1,testserver,backend}"
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"
export SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE:-false}"
export CSRF_COOKIE_SECURE="${CSRF_COOKIE_SECURE:-false}"
export AUTH_REFRESH_COOKIE_SECURE="${AUTH_REFRESH_COOKIE_SECURE:-false}"
export FORGEGRAPH_ALLOW_INSECURE_TRANSPORT="${FORGEGRAPH_ALLOW_INSECURE_TRANSPORT:-true}"
export ENGINE_CALLBACK_SECRET="${ENGINE_CALLBACK_SECRET:-local-production-evidence-engine-secret}"
export RUNTIME_TOOL_SECRET="${RUNTIME_TOOL_SECRET:-local-production-evidence-runtime-secret}"
export RUN_QUEUE_ENABLED="${RUN_QUEUE_ENABLED:-true}"
export AUTH_REGISTER_THROTTLE_RATE="${AUTH_REGISTER_THROTTLE_RATE:-10000/min}"
export AUTH_LOGIN_THROTTLE_RATE="${AUTH_LOGIN_THROTTLE_RATE:-10000/min}"
export AUTH_REFRESH_THROTTLE_RATE="${AUTH_REFRESH_THROTTLE_RATE:-10000/min}"
export AUTH_WS_TICKET_THROTTLE_RATE="${AUTH_WS_TICKET_THROTTLE_RATE:-10000/min}"
export API_ANON_THROTTLE_RATE="${API_ANON_THROTTLE_RATE:-10000/min}"
export API_USER_THROTTLE_RATE="${API_USER_THROTTLE_RATE:-10000/min}"
export RUN_START_RATE_LIMIT_PER_MIN="${RUN_START_RATE_LIMIT_PER_MIN:-10000}"
export RUN_INVOKE_RATE_LIMIT_PER_MIN="${RUN_INVOKE_RATE_LIMIT_PER_MIN:-10000}"
export RUN_MAX_ACTIVE_PER_TENANT="${RUN_MAX_ACTIVE_PER_TENANT:-250}"
export RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT="${RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT:-100}"

export PLAYWRIGHT_RUNTIME_TARGET="${PLAYWRIGHT_RUNTIME_TARGET:-docker}"
export PLAYWRIGHT_WORKERS="${PLAYWRIGHT_WORKERS:-1}"
export USE_SQLITE="${USE_SQLITE:-false}"
export USE_IN_MEMORY_CHANNEL_LAYER="${USE_IN_MEMORY_CHANNEL_LAYER:-false}"
export USE_IN_MEMORY_CACHE="${USE_IN_MEMORY_CACHE:-false}"
export PLAYWRIGHT_DOCKER_FRONTEND_URL="${PLAYWRIGHT_DOCKER_FRONTEND_URL:-http://127.0.0.1:3000}"
export PLAYWRIGHT_DOCKER_BACKEND_URL="${PLAYWRIGHT_DOCKER_BACKEND_URL:-http://127.0.0.1:8000}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"
export API_PROXY_TARGET="${API_PROXY_TARGET:-http://backend:8000}"
export PLAYWRIGHT_LLM_MOCK_PORT="${PLAYWRIGHT_LLM_MOCK_PORT:-8011}"
export PLAYWRIGHT_LLM_MOCK_URL="${PLAYWRIGHT_LLM_MOCK_URL:-http://127.0.0.1:${PLAYWRIGHT_LLM_MOCK_PORT}}"
export PLAYWRIGHT_LLM_MOCK_ERROR_MODE="${PLAYWRIGHT_LLM_MOCK_ERROR_MODE:-off}"
export PLAYWRIGHT_LOAD_SMOKE_RUNS="${PLAYWRIGHT_LOAD_SMOKE_RUNS:-100}"
export PLAYWRIGHT_LOAD_SMOKE_START_CONCURRENCY="${PLAYWRIGHT_LOAD_SMOKE_START_CONCURRENCY:-10}"

if [[ "${ROOT}" == /mnt/* ]]; then
  export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${HOME}/.cache/forgegraph/backend-venv}"
fi

LOCAL_GATE_BUILD="${LOCAL_GATE_BUILD:-true}"
LOCAL_GATE_RUN_TESTS="${LOCAL_GATE_RUN_TESTS:-true}"
LOCAL_GATE_DOWN_ON_EXIT="${LOCAL_GATE_DOWN_ON_EXIT:-false}"
LOCAL_GATE_INCLUDE_DOCKER_SMOKE="${LOCAL_GATE_INCLUDE_DOCKER_SMOKE:-true}"

LLM_MOCK_PID=""
PYTHON_CMD=()

detect_python() {
  if command -v python >/dev/null 2>&1; then
    PYTHON_CMD=(python)
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=(python3)
    return
  fi
  if command -v python.exe >/dev/null 2>&1; then
    PYTHON_CMD=(python.exe)
    return
  fi
  if command -v py >/dev/null 2>&1; then
    PYTHON_CMD=(py -3)
    return
  fi
  if command -v cmd.exe >/dev/null 2>&1; then
    PYTHON_CMD=(cmd.exe /c python)
    return
  fi
  echo "Missing required command: python" >&2
  exit 1
}

run_node() {
  if command -v node >/dev/null 2>&1; then
    node "$@"
    return
  fi
  if command -v node.exe >/dev/null 2>&1; then
    node.exe "$@"
    return
  fi
  if command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c node "$@"
    return
  fi
  echo "Missing required command: node" >&2
  return 127
}

compose() {
  DB_NAME="${DB_NAME}" \
    DB_USER="${DB_USER}" \
    DB_PASSWORD="${DB_PASSWORD}" \
    SECRET_KEY="${SECRET_KEY}" \
    ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
    ENGINE_CALLBACK_SECRET="${ENGINE_CALLBACK_SECRET}" \
    RUNTIME_TOOL_SECRET="${RUNTIME_TOOL_SECRET}" \
    DEBUG="${DEBUG}" \
    ALLOWED_HOSTS="${ALLOWED_HOSTS}" \
    SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT}" \
    SESSION_COOKIE_SECURE="${SESSION_COOKIE_SECURE}" \
    CSRF_COOKIE_SECURE="${CSRF_COOKIE_SECURE}" \
    AUTH_REFRESH_COOKIE_SECURE="${AUTH_REFRESH_COOKIE_SECURE}" \
    AUTH_REGISTER_THROTTLE_RATE="${AUTH_REGISTER_THROTTLE_RATE}" \
    AUTH_LOGIN_THROTTLE_RATE="${AUTH_LOGIN_THROTTLE_RATE}" \
    AUTH_REFRESH_THROTTLE_RATE="${AUTH_REFRESH_THROTTLE_RATE}" \
    AUTH_WS_TICKET_THROTTLE_RATE="${AUTH_WS_TICKET_THROTTLE_RATE}" \
    API_ANON_THROTTLE_RATE="${API_ANON_THROTTLE_RATE}" \
    API_USER_THROTTLE_RATE="${API_USER_THROTTLE_RATE}" \
    RUN_START_RATE_LIMIT_PER_MIN="${RUN_START_RATE_LIMIT_PER_MIN}" \
    RUN_INVOKE_RATE_LIMIT_PER_MIN="${RUN_INVOKE_RATE_LIMIT_PER_MIN}" \
    RUN_MAX_ACTIVE_PER_TENANT="${RUN_MAX_ACTIVE_PER_TENANT}" \
    RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT="${RUN_QUEUE_MAX_CONCURRENCY_PER_TENANT}" \
    FORGEGRAPH_ALLOW_INSECURE_TRANSPORT="${FORGEGRAPH_ALLOW_INSECURE_TRANSPORT}" \
    RUN_QUEUE_ENABLED="${RUN_QUEUE_ENABLED}" \
    REDIS_HOST="redis" \
    REDIS_PORT="6379" \
    REDIS_ADDR="redis:6379" \
    OPENAI_API_KEY="${OPENAI_API_KEY:-local-playwright-key}" \
    OPENAI_BASE_URL="http://host.docker.internal:${PLAYWRIGHT_LLM_MOCK_PORT}/v1" \
    NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL}" \
    API_PROXY_TARGET="${API_PROXY_TARGET}" \
    docker compose --profile queue "$@"
}

wait_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-90}"

  for _ in $(seq 1 "${attempts}"); do
    if http_ready "${url}"; then
      return 0
    fi
    sleep 2
  done

  echo "${label} did not become ready at ${url}" >&2
  compose ps || true
  exit 1
}

http_ready() {
  local url="$1"
  if "${PYTHON_CMD[@]}" - "$url" >/dev/null 2>&1 <<'PY'
import sys
from urllib.request import urlopen

url = sys.argv[1]
try:
    with urlopen(url, timeout=2) as response:
        raise SystemExit(0 if response.status < 500 else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    return 0
  fi

  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "${url}" >/dev/null 2>&1 && return 0
  fi
  if command -v curl.exe >/dev/null 2>&1; then
    curl.exe -fsS --max-time 2 "${url}" >/dev/null 2>&1 && return 0
  fi
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "\$ErrorActionPreference='Stop'; \$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '${url}'; if (\$r.StatusCode -lt 500) { exit 0 }; exit 1" >/dev/null 2>&1 && return 0
  fi

  return 1
}

detect_python

"${PYTHON_CMD[@]}" "${SCRIPT_DIR}/check_architecture_signoff.py" --require-approved

start_llm_mock() {
  if http_ready "${PLAYWRIGHT_LLM_MOCK_URL}/health"; then
    log_section "Reusing deterministic LLM mock at ${PLAYWRIGHT_LLM_MOCK_URL}"
    return
  fi

  log_section "Start deterministic LLM mock"
  (
    cd "${ROOT}/frontend"
    PLAYWRIGHT_LLM_MOCK_PORT="${PLAYWRIGHT_LLM_MOCK_PORT}" \
      PLAYWRIGHT_LLM_MOCK_ERROR_MODE="${PLAYWRIGHT_LLM_MOCK_ERROR_MODE}" \
      run_node scripts/playwright-openai-mock.mjs
  ) &
  LLM_MOCK_PID="$!"
  wait_http "${PLAYWRIGHT_LLM_MOCK_URL}/health" "Deterministic LLM mock" 30
}

cleanup() {
  local exit_code=$?
  if [[ -n "${LLM_MOCK_PID}" ]]; then
    if [[ "${LOCAL_GATE_RUN_TESTS}" == "false" && "${LOCAL_GATE_DOWN_ON_EXIT}" != "true" ]]; then
      echo "Deterministic LLM mock left running with PID ${LLM_MOCK_PID}."
    else
      kill "${LLM_MOCK_PID}" >/dev/null 2>&1 || true
    fi
  fi
  if [[ "${LOCAL_GATE_DOWN_ON_EXIT}" == "true" ]]; then
    compose down --remove-orphans
  elif [[ "${exit_code}" != "0" ]]; then
    echo "Local production evidence gate failed. Docker services are left running for inspection." >&2
    echo "Use: docker compose --profile queue logs --tail=200" >&2
  fi
}
trap cleanup EXIT

log_section "Start Postgres and Redis"
compose up -d postgres redis
require_tcp_service "${DB_HOST}" "${DB_PORT}" "Postgres"
require_tcp_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

log_section "Apply backend migrations to local evidence database"
(
  cd "${ROOT}/backend"
  require_uv
  run_uv run python manage.py migrate --noinput
)

start_llm_mock

log_section "Start full Docker stack"
compose_up_args=(up -d)
if [[ "${LOCAL_GATE_BUILD}" == "true" ]]; then
  compose_up_args+=(--build)
fi
compose "${compose_up_args[@]}" memory-grpc engine backend backend-runtime-intents backend-run-queue frontend

wait_http "http://127.0.0.1:8000/health" "Backend/Daphne/WebSocket server" 120
wait_http "http://127.0.0.1:3000/" "Frontend" 120
wait_http "http://127.0.0.1:9090/ready" "Engine metrics/readiness" 120

if [[ "${LOCAL_GATE_RUN_TESTS}" != "true" ]]; then
  log_section "Full stack is running; tests skipped by LOCAL_GATE_RUN_TESTS=false"
  exit 0
fi

log_section "Run production evidence gate"
RUN_REQUIRED_CHECKS_INCLUDE_DOCKER_SMOKE=false bash "${SCRIPT_DIR}/run_required_checks.sh"

if [[ "${LOCAL_GATE_INCLUDE_DOCKER_SMOKE}" == "true" ]]; then
  log_section "Stop compose app services before Docker image smoke"
  compose stop frontend backend backend-runtime-intents backend-run-queue engine memory-grpc >/dev/null

  log_section "Run Docker image full-stack smoke"
  bash "${SCRIPT_DIR}/run_docker_full_stack_smoke.sh"
fi

log_section "Local production evidence gate completed"
