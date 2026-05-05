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

if [[ "${ENGINE_CHANGED}" != "1" ]]; then
  log_section "Engine fast checks"
  echo "No engine changes detected; skipping."
  exit 0
fi

cd "${ROOT}/engine"

require_command go
require_command gofmt

mapfile -t changed_go_files < <(grep -E '\.go$' "${TMP_DIR}/engine_files.txt" || true)

log_section "Engine gofmt"
if [[ ${#changed_go_files[@]} -eq 0 ]]; then
  echo "No changed Go files detected; skipping gofmt."
else
  changed_go_rel=()
  for file in "${changed_go_files[@]}"; do
    rel="${file#engine/}"
    if [[ -f "${rel}" ]]; then
      changed_go_rel+=("${rel}")
    fi
  done
  if [[ ${#changed_go_rel[@]} -eq 0 ]]; then
    echo "No changed existing Go files detected; skipping gofmt."
  else
    unformatted="$(gofmt -l "${changed_go_rel[@]}")"
    if [[ -n "${unformatted}" ]]; then
      echo "gofmt required on:" >&2
      echo "${unformatted}" >&2
      exit 1
    fi
  fi
fi

bash "${ROOT}/scripts/check_engine_statelessness.sh"
run_python "${SCRIPT_DIR}/check_engine_no_release_sleeps.py"
bash "${SCRIPT_DIR}/check_engine_ownership.sh"
bash "${SCRIPT_DIR}/check_engine_event_envelope.sh"

engine_impacted_packages() {
  local changed_packages=()
  local line=""

  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    [[ "${line}" == *.go ]] || continue
    local rel="${line#engine/}"
    local dir
    dir="$(dirname "${rel}")"
    local pkg=""
    pkg="$(go list "./${dir}" 2>/dev/null || true)"
    if [[ -n "${pkg}" ]]; then
      changed_packages+=("${pkg}")
    fi
  done < "${TMP_DIR}/engine_files.txt"

  if [[ ${#changed_packages[@]} -eq 0 ]]; then
    return 0
  fi

  mapfile -t changed_packages < <(printf '%s\n' "${changed_packages[@]}" | sort -u)

  go list -f '{{printf "%s|" .ImportPath}}{{range .Deps}}{{printf "%s " .}}{{end}}' ./... \
    | while IFS='|' read -r pkg deps; do
        for changed_pkg in "${changed_packages[@]}"; do
          if [[ "${pkg}" == "${changed_pkg}" ]] || [[ " ${deps} " == *" ${changed_pkg} "* ]]; then
            printf '%s\n' "${pkg}"
            break
          fi
        done
      done \
    | sort -u
}

if [[ "${ENGINE_HIGH_RISK}" == "1" ]]; then
  log_section "Engine vet"
  go vet ./...

  log_section "Engine tests"
  go test ./...
else
  mapfile -t impacted_packages < <(engine_impacted_packages)

  if [[ ${#impacted_packages[@]} -eq 0 ]]; then
    log_section "Engine tests"
    echo "No impacted Go packages detected; skipping go vet/go test."
  else
    log_section "Engine vet"
    go vet "${impacted_packages[@]}"

    log_section "Engine tests"
    go test "${impacted_packages[@]}"
  fi
fi

log_section "Launch QA engine"
bash "${SCRIPT_DIR}/run_launch_qa_engine.sh"
