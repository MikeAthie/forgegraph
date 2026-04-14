#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "${ROOT}/backend"

python manage.py validate_runtime_env --strict
python manage.py migrate --noinput
python manage.py collectstatic --noinput

