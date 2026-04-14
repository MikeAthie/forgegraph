#!/usr/bin/env bash
set -euo pipefail

OUTPUT_PATH="${1:-backups/forgegraph-$(date -u +%Y%m%dT%H%M%SZ).dump}"
mkdir -p "$(dirname "${OUTPUT_PATH}")"

if [[ -n "${DATABASE_URL:-}" ]]; then
  pg_dump --format=custom --no-owner --no-privileges --file "${OUTPUT_PATH}" "${DATABASE_URL}"
else
  : "${PGHOST:?PGHOST is required when DATABASE_URL is unset}"
  : "${PGPORT:?PGPORT is required when DATABASE_URL is unset}"
  : "${PGUSER:?PGUSER is required when DATABASE_URL is unset}"
  : "${PGPASSWORD:?PGPASSWORD is required when DATABASE_URL is unset}"
  : "${PGDATABASE:?PGDATABASE is required when DATABASE_URL is unset}"
  export PGPASSWORD
  pg_dump \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file "${OUTPUT_PATH}" \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    "${PGDATABASE}"
fi

echo "Backup written to ${OUTPUT_PATH}"

