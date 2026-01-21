#!/bin/bash
set -e

echo "Syncing dependencies..."
uv sync --frozen --no-dev --no-install-project

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Ensuring superuser exists..."
python manage.py ensure_superuser

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"
