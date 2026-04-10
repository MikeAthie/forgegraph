#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
OUT_DIR="${1:?usage: detect_changed_scopes.sh <output-dir>}"

mkdir -p "${OUT_DIR}"
cd "${ROOT}"

: > "${OUT_DIR}/backend_files.txt"
: > "${OUT_DIR}/engine_files.txt"
: > "${OUT_DIR}/frontend_files.txt"

resolve_base_ref() {
  if [[ -n "${FORGEGRAPH_DIFF_BASE:-}" ]]; then
    echo "${FORGEGRAPH_DIFF_BASE}"
    return
  fi

  if [[ -n "${GITHUB_BASE_REF:-}" ]]; then
    if git rev-parse --verify "origin/${GITHUB_BASE_REF}" >/dev/null 2>&1; then
      echo "origin/${GITHUB_BASE_REF}"
      return
    fi
    if git rev-parse --verify "${GITHUB_BASE_REF}" >/dev/null 2>&1; then
      echo "${GITHUB_BASE_REF}"
      return
    fi
  fi

  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "origin/main"
    return
  fi

  if git rev-parse --verify main >/dev/null 2>&1; then
    echo "main"
    return
  fi

  if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
    echo "HEAD~1"
    return
  fi

  echo ""
}

collect_changed_files() {
  local base_ref="$1"

  if [[ -n "${base_ref}" ]]; then
    git diff --name-only "${base_ref}...HEAD" 2>/dev/null || true
  fi

  git diff --name-only 2>/dev/null || true
  git diff --name-only --cached 2>/dev/null || true
  git ls-files --others --exclude-standard 2>/dev/null || true
}

is_backend_high_risk() {
  local file="$1"
  [[ "${file}" == "backend/pyproject.toml" ]] && return 0
  [[ "${file}" == "backend/pytest.ini" ]] && return 0
  [[ "${file}" == "backend/manage.py" ]] && return 0
  [[ "${file}" == "backend/uv.lock" ]] && return 0
  [[ "${file}" == backend/config/* ]] && return 0
  [[ "${file}" == backend/infrastructure/orm/migrations/* ]] && return 0
  [[ "${file}" == backend/scripts/* ]] && return 0
  [[ "${file}" == "backend/tests/conftest.py" ]] && return 0
  [[ "${file}" =~ ^backend/tests/.+/conftest\.py$ ]] && return 0
  return 1
}

is_engine_high_risk() {
  local file="$1"
  [[ "${file}" == "engine/go.mod" ]] && return 0
  [[ "${file}" == "engine/go.sum" ]] && return 0
  [[ "${file}" == engine/proto/* ]] && return 0
  return 1
}

is_frontend_high_risk() {
  local file="$1"
  [[ "${file}" == "frontend/package.json" ]] && return 0
  [[ "${file}" == "frontend/package-lock.json" ]] && return 0
  [[ "${file}" == "frontend/jest.config.js" ]] && return 0
  [[ "${file}" == "frontend/jest.setup.js" ]] && return 0
  [[ "${file}" == "frontend/next.config.js" ]] && return 0
  [[ "${file}" == "frontend/tsconfig.json" ]] && return 0
  return 1
}

frontend_requires_build() {
  local file="$1"
  [[ "${file}" == frontend/__tests__/* ]] && return 1
  [[ "${file}" == "frontend/e2e-report.json" ]] && return 1
  [[ "${file}" == frontend/testsprite_tests/* ]] && return 1
  [[ "${file}" == frontend/playwright* ]] && return 1
  return 0
}

BASE_REF="$(resolve_base_ref)"
mapfile -t CHANGED_FILES < <(collect_changed_files "${BASE_REF}" | awk 'NF' | sort -u)

BACKEND_CHANGED=0
ENGINE_CHANGED=0
FRONTEND_CHANGED=0
BACKEND_HIGH_RISK=0
ENGINE_HIGH_RISK=0
FRONTEND_HIGH_RISK=0
FRONTEND_BUILD_REQUIRED=0

for file in "${CHANGED_FILES[@]}"; do
  case "${file}" in
    backend/*)
      BACKEND_CHANGED=1
      printf '%s\n' "${file}" >> "${OUT_DIR}/backend_files.txt"
      if is_backend_high_risk "${file}"; then
        BACKEND_HIGH_RISK=1
      fi
      ;;
    engine/*)
      ENGINE_CHANGED=1
      printf '%s\n' "${file}" >> "${OUT_DIR}/engine_files.txt"
      if is_engine_high_risk "${file}"; then
        ENGINE_HIGH_RISK=1
      fi
      ;;
    frontend/*)
      FRONTEND_CHANGED=1
      printf '%s\n' "${file}" >> "${OUT_DIR}/frontend_files.txt"
      if is_frontend_high_risk "${file}"; then
        FRONTEND_HIGH_RISK=1
      fi
      if frontend_requires_build "${file}"; then
        FRONTEND_BUILD_REQUIRED=1
      fi
      ;;
  esac
done

{
  printf 'export DIFF_BASE_REF=%q\n' "${BASE_REF}"
  printf 'export HAS_CHANGES=%q\n' "$([[ ${#CHANGED_FILES[@]} -gt 0 ]] && echo 1 || echo 0)"
  printf 'export BACKEND_CHANGED=%q\n' "${BACKEND_CHANGED}"
  printf 'export ENGINE_CHANGED=%q\n' "${ENGINE_CHANGED}"
  printf 'export FRONTEND_CHANGED=%q\n' "${FRONTEND_CHANGED}"
  printf 'export BACKEND_HIGH_RISK=%q\n' "${BACKEND_HIGH_RISK}"
  printf 'export ENGINE_HIGH_RISK=%q\n' "${ENGINE_HIGH_RISK}"
  printf 'export FRONTEND_HIGH_RISK=%q\n' "${FRONTEND_HIGH_RISK}"
  printf 'export FRONTEND_BUILD_REQUIRED=%q\n' "${FRONTEND_BUILD_REQUIRED}"
} > "${OUT_DIR}/scopes.env"
