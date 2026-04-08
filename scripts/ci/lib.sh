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

export_backend_ci_env() {
  export DB_HOST="${DB_HOST:-localhost}"
  export DB_PORT="${DB_PORT:-5433}"
  export DB_NAME="${DB_NAME:-forgegraph}"
  export DB_USER="${DB_USER:-forgegraph}"
  export DB_PASSWORD="${DB_PASSWORD:-forgegraph_secret}"
  export REDIS_HOST="${REDIS_HOST:-localhost}"
  export REDIS_PORT="${REDIS_PORT:-6379}"
  export SECRET_KEY="${SECRET_KEY:-ci-not-a-secret}"
  export DEBUG="${DEBUG:-False}"
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"
  export ALLOWED_HOSTS="${ALLOWED_HOSTS:-localhost}"
  export ENCRYPTION_KEY="${ENCRYPTION_KEY:-31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=}"
  export SECURE_SSL_REDIRECT="${SECURE_SSL_REDIRECT:-false}"
}

