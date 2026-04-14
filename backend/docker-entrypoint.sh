#!/bin/bash
set -e

echo "Validating runtime environment..."
python manage.py validate_runtime_env --strict

echo "Starting server..."
exec "$@"
