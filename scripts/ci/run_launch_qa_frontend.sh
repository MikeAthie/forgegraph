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
  __tests__/unit/pages/operations.test.tsx \
  __tests__/unit/pages/departments.test.tsx \
  __tests__/unit/pages/memory.test.tsx \
  __tests__/unit/pages/admin-operations.test.tsx \
  __tests__/unit/pages/admin-audit-logs.test.tsx \
  __tests__/unit/pages/admin-billing.test.tsx \
  __tests__/unit/components/OsShell.test.tsx \
  __tests__/unit/components/ProtectedRoute.test.tsx
