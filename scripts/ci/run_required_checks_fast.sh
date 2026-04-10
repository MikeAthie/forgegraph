#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${SCRIPT_DIR}/run_backend_checks_fast.sh"
bash "${SCRIPT_DIR}/run_engine_checks_fast.sh"
bash "${SCRIPT_DIR}/run_frontend_checks_fast.sh"
