#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${SCRIPT_DIR}/run_backend_checks.sh"
bash "${SCRIPT_DIR}/run_engine_checks.sh"
bash "${SCRIPT_DIR}/run_frontend_checks.sh"
bash "${SCRIPT_DIR}/run_launch_qa_backend.sh"
bash "${SCRIPT_DIR}/run_launch_qa_engine.sh"
bash "${SCRIPT_DIR}/run_launch_qa_frontend.sh"
