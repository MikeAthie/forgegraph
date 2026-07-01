#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}"

require_command docker

export BACKEND_IMAGE="${BACKEND_IMAGE:-forgegraph/backend:ci-smoke}"
export ENGINE_IMAGE="${ENGINE_IMAGE:-forgegraph/engine:ci-smoke}"
export FRONTEND_IMAGE="${FRONTEND_IMAGE:-forgegraph/frontend:ci-smoke}"
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-5433}"
if [[ -z "${DB_NAME:-}" ]]; then
  export DB_NAME="forgegraph_ci_smoke_$(date +%s)_$$"
  DOCKER_SMOKE_OWNS_DB=true
else
  export DB_NAME
  DOCKER_SMOKE_OWNS_DB=false
fi
export DB_USER="${DB_USER:-forgegraph}"
export DB_PASSWORD="${DB_PASSWORD:-forgegraph_secret}"
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_ADDR="${REDIS_ADDR:-${REDIS_HOST}:${REDIS_PORT}}"
export SECRET_KEY="${SECRET_KEY:-docker-ci-not-a-secret}"
export DEBUG="${DEBUG:-False}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-127.0.0.1,localhost}"
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=}"
export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"
export FORGEGRAPH_ALLOW_INSECURE_TRANSPORT="${FORGEGRAPH_ALLOW_INSECURE_TRANSPORT:-true}"
export ENGINE_CALLBACK_SECRET="${ENGINE_CALLBACK_SECRET:-docker-ci-shared-secret}"
export RUNTIME_TOOL_SECRET="${RUNTIME_TOOL_SECRET:-docker-ci-runtime-tool-secret}"
export DOCKER_SMOKE_BACKEND_PORT="${DOCKER_SMOKE_BACKEND_PORT:-8010}"
export DOCKER_SMOKE_FRONTEND_PORT="${DOCKER_SMOKE_FRONTEND_PORT:-3010}"
export DOCKER_SMOKE_ENGINE_PORT="${DOCKER_SMOKE_ENGINE_PORT:-50151}"
export DOCKER_SMOKE_ENGINE_METRICS_PORT="${DOCKER_SMOKE_ENGINE_METRICS_PORT:-19090}"
export ENGINE_CALLBACK_URL="${ENGINE_CALLBACK_URL:-http://127.0.0.1:${DOCKER_SMOKE_BACKEND_PORT}/api/runs/engine-events}"
export CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:${DOCKER_SMOKE_BACKEND_PORT}}"
export ENGINE_HOST="${DOCKER_SMOKE_ENGINE_HOST:-127.0.0.1}"
export ENGINE_PORT="${DOCKER_SMOKE_ENGINE_PORT}"
export ENGINE_INSTANCE_ID="${DOCKER_SMOKE_ENGINE_INSTANCE_ID:-${ENGINE_HOST}:${ENGINE_PORT}}"
export READINESS_REQUIRE_ENGINE="${READINESS_REQUIRE_ENGINE:-true}"
export READINESS_REQUIRE_RUNTIME_TRANSPORT="${READINESS_REQUIRE_RUNTIME_TRANSPORT:-true}"
export FORGEGRAPH_STRICT_RUNTIME_ENV="${FORGEGRAPH_STRICT_RUNTIME_ENV:-true}"
export RUN_QUEUE_ENABLED="${RUN_QUEUE_ENABLED:-true}"
export API_PROXY_TARGET="${DOCKER_SMOKE_API_PROXY_TARGET:-http://127.0.0.1:${DOCKER_SMOKE_BACKEND_PORT}}"
export FORGEGRAPH_RUNTIME_INTENT_STREAM="${FORGEGRAPH_RUNTIME_INTENT_STREAM:-forgegraph:runtime:intents:ci-smoke}"
export FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM="${FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM:-forgegraph:runtime:intents:ci-smoke:dead}"
export FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP="${FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP:-backend-runtime-writers-ci-smoke}"
export ENGINE_RUNTIME_INTENT_STREAM="${ENGINE_RUNTIME_INTENT_STREAM:-${FORGEGRAPH_RUNTIME_INTENT_STREAM}}"
export OPERATING_MODEL_PACKS_DIR="${OPERATING_MODEL_PACKS_DIR:-/operating_model_packs}"
export REQUIRED_OPERATING_MODEL_PACKS="${REQUIRED_OPERATING_MODEL_PACKS:-digital_marketing_pro}"

containers=(
  forgegraph-ci-backend
  forgegraph-ci-engine
  forgegraph-ci-run-queue
  forgegraph-ci-runtime-intents
  forgegraph-ci-frontend
)

cleanup() {
  local exit_code=$?
  if [[ "${exit_code}" != "0" ]]; then
    for container in "${containers[@]}"; do
      docker logs "${container}" || true
    done
  fi
  docker rm -f "${containers[@]}" >/dev/null 2>&1 || true
  if [[ "${DOCKER_SMOKE_OWNS_DB}" == "true" ]]; then
    drop_smoke_database || true
  fi
}
trap cleanup EXIT

create_smoke_database() {
  docker run --rm -i --network host --entrypoint python \
    -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
    "${BACKEND_IMAGE}" - <<'PY'
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

drop_smoke_database() {
  docker run --rm -i --network host --entrypoint python \
    -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
    "${BACKEND_IMAGE}" - <<'PY'
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

log_section "Build backend image"
docker build -t "${BACKEND_IMAGE}" backend

if [[ "${DOCKER_SMOKE_OWNS_DB}" == "true" ]]; then
  log_section "Create Docker smoke database"
  create_smoke_database
fi

log_section "Build engine image"
docker build -t "${ENGINE_IMAGE}" engine

log_section "Build frontend image"
docker build \
  --build-arg NEXT_PUBLIC_API_URL="http://127.0.0.1:${DOCKER_SMOKE_BACKEND_PORT}" \
  --build-arg API_PROXY_TARGET="${API_PROXY_TARGET}" \
  -t "${FRONTEND_IMAGE}" frontend

log_section "Run migration contract"
docker run --rm --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -v "${ROOT}/operating_model_packs:${OPERATING_MODEL_PACKS_DIR}:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT -e ENGINE_INSTANCE_ID \
  -e FRONTEND_URL="http://127.0.0.1:${DOCKER_SMOKE_FRONTEND_PORT}" \
  -e FORGEGRAPH_RUNTIME_INTENT_STREAM -e FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM \
  -e FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP \
  -e OPERATING_MODEL_PACKS_DIR -e REQUIRED_OPERATING_MODEL_PACKS \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT \
  "${BACKEND_IMAGE}" bash -c "python manage.py validate_runtime_env --strict && python manage.py migrate --noinput && python manage.py collectstatic --noinput"

log_section "Start Dockerized stack"
docker run -d --name forgegraph-ci-backend --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -v "${ROOT}/operating_model_packs:${OPERATING_MODEL_PACKS_DIR}:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT -e ENGINE_INSTANCE_ID \
  -e FRONTEND_URL="http://127.0.0.1:${DOCKER_SMOKE_FRONTEND_PORT}" \
  -e FORGEGRAPH_RUNTIME_INTENT_STREAM -e FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM \
  -e FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP \
  -e OPERATING_MODEL_PACKS_DIR -e REQUIRED_OPERATING_MODEL_PACKS \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT -e RUN_QUEUE_ENABLED \
  "${BACKEND_IMAGE}" daphne -b 0.0.0.0 -p "${DOCKER_SMOKE_BACKEND_PORT}" config.asgi:application

docker run -d --name forgegraph-ci-engine --network host \
  -e CONTROL_PLANE_URL -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e REDIS_ADDR -e REDIS_HOST -e REDIS_PORT \
  -e ENGINE_CALLBACK_URL -e ENGINE_RUNTIME_INTENT_STREAM -e ENGINE_HOST -e ENGINE_INSTANCE_ID \
  -e ENGINE_RUN_STATE_MODE=control-plane-http \
  -e GRPC_PORT="${DOCKER_SMOKE_ENGINE_PORT}" -e METRICS_PORT="${DOCKER_SMOKE_ENGINE_METRICS_PORT}" \
  "${ENGINE_IMAGE}"

docker run -d --name forgegraph-ci-run-queue --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -v "${ROOT}/operating_model_packs:${OPERATING_MODEL_PACKS_DIR}:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT -e ENGINE_INSTANCE_ID \
  -e FRONTEND_URL="http://127.0.0.1:${DOCKER_SMOKE_FRONTEND_PORT}" \
  -e FORGEGRAPH_RUNTIME_INTENT_STREAM -e FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM \
  -e FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP \
  -e OPERATING_MODEL_PACKS_DIR -e REQUIRED_OPERATING_MODEL_PACKS \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT -e RUN_QUEUE_ENABLED \
  "${BACKEND_IMAGE}" python manage.py process_run_queue --worker-id ci-docker-run-queue

docker run -d --name forgegraph-ci-runtime-intents --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -v "${ROOT}/operating_model_packs:${OPERATING_MODEL_PACKS_DIR}:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT -e ENGINE_INSTANCE_ID \
  -e FRONTEND_URL="http://127.0.0.1:${DOCKER_SMOKE_FRONTEND_PORT}" \
  -e FORGEGRAPH_RUNTIME_INTENT_STREAM -e FORGEGRAPH_RUNTIME_INTENT_DEAD_LETTER_STREAM \
  -e FORGEGRAPH_RUNTIME_INTENT_CONSUMER_GROUP \
  -e OPERATING_MODEL_PACKS_DIR -e REQUIRED_OPERATING_MODEL_PACKS \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT -e RUN_QUEUE_ENABLED \
  "${BACKEND_IMAGE}" python manage.py process_runtime_write_intents --consumer ci-docker-runtime-intents

docker run -d --name forgegraph-ci-frontend --network host \
  -e API_PROXY_TARGET -e PORT="${DOCKER_SMOKE_FRONTEND_PORT}" \
  "${FRONTEND_IMAGE}"

log_section "Docker full-stack smoke"
docker run --rm --network host \
  --entrypoint python \
  -v "${ROOT}:/workspace:ro" \
  -w /workspace \
  "${BACKEND_IMAGE}" \
  scripts/release/backend_smoke.py \
  --backend-url "http://127.0.0.1:${DOCKER_SMOKE_BACKEND_PORT}" \
  --frontend-url "http://127.0.0.1:${DOCKER_SMOKE_FRONTEND_PORT}" \
  --engine-url "http://127.0.0.1:${DOCKER_SMOKE_ENGINE_METRICS_PORT}" \
  --callback-secret "${ENGINE_CALLBACK_SECRET}" \
  --engine-instance-id "${ENGINE_INSTANCE_ID}"
