#!/usr/bin/env bash
set -euo pipefail

INPUT_PATH="${1:-}"
if [[ -z "${INPUT_PATH}" ]]; then
  echo "Usage: $0 <backup.dump>" >&2
  exit 1
fi

if [[ ! -f "${INPUT_PATH}" ]]; then
  echo "Backup file not found: ${INPUT_PATH}" >&2
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  TARGET_URL="${DATABASE_URL}"
  python - "${TARGET_URL}" "${INPUT_PATH}" <<'PY'
import subprocess
import sys
from urllib.parse import urlparse

target_url = sys.argv[1]
backup_path = sys.argv[2]
parsed = urlparse(target_url)
dbname = parsed.path.lstrip("/")
admin_url = parsed._replace(path="/postgres").geturl()

subprocess.run(["psql", admin_url, "-c", f"DROP DATABASE IF EXISTS {dbname};"], check=True)
subprocess.run(["psql", admin_url, "-c", f"CREATE DATABASE {dbname};"], check=True)
subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges", "-d", target_url, backup_path], check=True)
PY
else
  : "${PGHOST:?PGHOST is required when DATABASE_URL is unset}"
  : "${PGPORT:?PGPORT is required when DATABASE_URL is unset}"
  : "${PGUSER:?PGUSER is required when DATABASE_URL is unset}"
  : "${PGPASSWORD:?PGPASSWORD is required when DATABASE_URL is unset}"
  : "${PGDATABASE:?PGDATABASE is required when DATABASE_URL is unset}"
  export PGPASSWORD
  psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "DROP DATABASE IF EXISTS ${PGDATABASE};"
  psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "CREATE DATABASE ${PGDATABASE};"
  pg_restore \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    -h "${PGHOST}" \
    -p "${PGPORT}" \
    -U "${PGUSER}" \
    -d "${PGDATABASE}" \
    "${INPUT_PATH}"
fi

echo "Restore completed from ${INPUT_PATH}"

