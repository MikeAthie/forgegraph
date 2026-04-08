#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/ci/lib.sh
source "${SCRIPT_DIR}/lib.sh"

ROOT="$(forgegraph_repo_root)"
cd "${ROOT}/frontend"

require_command npx

log_section "Launch QA frontend"
npx jest --runInBand \
  __tests__/components/graph-editor/GraphEditor.test.tsx \
  __tests__/components/graph-editor/wizard/AgentWizard.test.tsx \
  __tests__/components/graph-editor/NodeConfigDialog.test.tsx

