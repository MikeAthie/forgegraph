#!/usr/bin/env bash
set -euo pipefail

forgegraph_repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

log_section() {
  printf '\n==> %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    python -m uv --help >/dev/null 2>&1 && return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -m uv --help >/dev/null 2>&1 && return 0
  fi
  echo "Missing required command: uv" >&2
  exit 1
}

run_uv() {
  if command -v uv >/dev/null 2>&1; then
    uv "$@"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    python -m uv "$@"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -m uv "$@"
    return
  fi
  echo "Missing required command: uv" >&2
  exit 1
}

require_tcp_service() {
  local host="$1"
  local port="$2"
  local label="$3"

  if ! (echo >"/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
    echo "${label} is not reachable at ${host}:${port}" >&2
    echo "Start the local dependencies before pushing." >&2
    exit 1
  fi
}

load_env_file() {
  local env_file="$1"
  if [[ ! -f "${env_file}" ]]; then
    return 0
  fi

  set -a
  # shellcheck disable=SC1090
  source "${env_file}"
  set +a
}

export_backend_ci_env() {
  local root
  root="$(forgegraph_repo_root)"
  load_env_file "${root}/.env.test"

  export FORGEGRAPH_ENV_FILE="${FORGEGRAPH_ENV_FILE:-.env.test}"
  export TESTING="${TESTING:-true}"
  export DB_HOST="${DB_HOST:-localhost}"
  export DB_PORT="${DB_PORT:-5433}"
  export DB_NAME="${DB_NAME:-forgegraph}"
  export DB_USER="${DB_USER:-forgegraph}"
  export DB_PASSWORD="${DB_PASSWORD:-forgegraph_secret}"
  export REDIS_HOST="${REDIS_HOST:-localhost}"
  export REDIS_PORT="${REDIS_PORT:-6379}"
  export SECRET_KEY="${SECRET_KEY:-ci-not-a-secret}"
  export DEBUG="${DEBUG:-False}"
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.test_settings}"
  export ALLOWED_HOSTS="${ALLOWED_HOSTS:-localhost,127.0.0.1,testserver}"
  export ENCRYPTION_KEY="${ENCRYPTION_KEY:-31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=}"
  export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"
  export FORGEGRAPH_ALLOW_INSECURE_TRANSPORT="${FORGEGRAPH_ALLOW_INSECURE_TRANSPORT:-true}"
  export ENGINE_CALLBACK_SECRET="${ENGINE_CALLBACK_SECRET:-ci-engine-callback-secret}"
  export RUNTIME_TOOL_SECRET="${RUNTIME_TOOL_SECRET:-ci-runtime-tool-secret}"

  # On WSL with the repo mounted from Windows, keep uv's environment off /mnt/*
  # to avoid mutating a Windows-created .venv from Linux.
  if [[ "${root}" == /mnt/* ]]; then
    export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${HOME}/.cache/forgegraph/backend-venv}"
  fi
}

go_race_supported() {
  local goos
  goos="$(go env GOOS 2>/dev/null || true)"
  case "${goos}" in
    windows)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

run_go_race_or_skip() {
  if go_race_supported; then
    CGO_ENABLED=1 go test -race "$@"
    return
  fi

  echo "Skipping Go race tests on GOOS=$(go env GOOS 2>/dev/null || echo unknown)." >&2
  echo "The local Windows ThreadSanitizer runtime is not reliable for this check; Linux CI remains authoritative." >&2
}
