#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
git config core.hooksPath "${ROOT}/.githooks"
echo "Configured core.hooksPath=${ROOT}/.githooks"

