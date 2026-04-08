#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/frontend"

require_command npm

log_section "Frontend format"
npm run format:check

log_section "Frontend lint"
npm run lint

log_section "Frontend unit tests"
npm test

log_section "Frontend build"
npm run build

