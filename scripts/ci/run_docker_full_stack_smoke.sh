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
export DB_NAME="${DB_NAME:-forgegraph}"
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
export ENGINE_CALLBACK_URL="${ENGINE_CALLBACK_URL:-http://127.0.0.1:8000/api/runs/engine-events}"
export CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
export ENGINE_HOST="${ENGINE_HOST:-127.0.0.1}"
export ENGINE_PORT="${ENGINE_PORT:-50051}"
export READINESS_REQUIRE_ENGINE="${READINESS_REQUIRE_ENGINE:-true}"
export READINESS_REQUIRE_RUNTIME_TRANSPORT="${READINESS_REQUIRE_RUNTIME_TRANSPORT:-true}"
export FORGEGRAPH_STRICT_RUNTIME_ENV="${FORGEGRAPH_STRICT_RUNTIME_ENV:-true}"
export RUN_QUEUE_ENABLED="${RUN_QUEUE_ENABLED:-true}"
export API_PROXY_TARGET="${DOCKER_SMOKE_API_PROXY_TARGET:-http://127.0.0.1:8000}"

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
}
trap cleanup EXIT

log_section "Build backend image"
docker build -t "${BACKEND_IMAGE}" backend

log_section "Build engine image"
docker build -t "${ENGINE_IMAGE}" engine

log_section "Build frontend image"
docker build \
  --build-arg NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 \
  --build-arg API_PROXY_TARGET="${API_PROXY_TARGET}" \
  -t "${FRONTEND_IMAGE}" frontend

log_section "Run migration contract"
docker run --rm --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT \
  -e FRONTEND_URL=http://127.0.0.1:3000 \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT \
  "${BACKEND_IMAGE}" bash -c "python manage.py validate_runtime_env --strict && python manage.py migrate --noinput && python manage.py collectstatic --noinput"

log_section "Start Dockerized stack"
docker run -d --name forgegraph-ci-backend --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT \
  -e FRONTEND_URL=http://127.0.0.1:3000 \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT -e RUN_QUEUE_ENABLED \
  "${BACKEND_IMAGE}"

docker run -d --name forgegraph-ci-engine --network host \
  -e CONTROL_PLANE_URL -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e REDIS_ADDR -e REDIS_HOST -e REDIS_PORT \
  -e ENGINE_CALLBACK_URL \
  -e ENGINE_RUN_STATE_MODE=control-plane-http \
  -e GRPC_PORT=50051 -e METRICS_PORT=9090 \
  "${ENGINE_IMAGE}"

docker run -d --name forgegraph-ci-run-queue --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT \
  -e FRONTEND_URL=http://127.0.0.1:3000 \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT -e RUN_QUEUE_ENABLED \
  "${BACKEND_IMAGE}" python manage.py process_run_queue --worker-id ci-docker-run-queue

docker run -d --name forgegraph-ci-runtime-intents --network host \
  -v "${ROOT}/docs:/docs:ro" \
  -e DB_HOST -e DB_PORT -e DB_NAME -e DB_USER -e DB_PASSWORD \
  -e REDIS_HOST -e REDIS_PORT -e SECRET_KEY -e DEBUG -e DJANGO_SETTINGS_MODULE \
  -e ALLOWED_HOSTS -e ENCRYPTION_KEY -e SECURE_SSL_REDIRECT \
  -e FORGEGRAPH_ALLOW_INSECURE_TRANSPORT \
  -e ENGINE_CALLBACK_SECRET -e RUNTIME_TOOL_SECRET \
  -e ENGINE_CALLBACK_URL -e ENGINE_HOST -e ENGINE_PORT \
  -e FRONTEND_URL=http://127.0.0.1:3000 \
  -e FORGEGRAPH_STRICT_RUNTIME_ENV -e READINESS_REQUIRE_ENGINE \
  -e READINESS_REQUIRE_RUNTIME_TRANSPORT -e RUN_QUEUE_ENABLED \
  "${BACKEND_IMAGE}" python manage.py process_runtime_write_intents --consumer ci-docker-runtime-intents

docker run -d --name forgegraph-ci-frontend --network host \
  -e API_PROXY_TARGET \
  "${FRONTEND_IMAGE}"

log_section "Docker full-stack smoke"
docker run --rm --network host \
  --entrypoint python \
  -v "${ROOT}:/workspace:ro" \
  -w /workspace \
  "${BACKEND_IMAGE}" \
  scripts/release/backend_smoke.py \
  --backend-url http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1:3000 \
  --engine-url http://127.0.0.1:9090 \
  --callback-secret "${ENGINE_CALLBACK_SECRET}"
