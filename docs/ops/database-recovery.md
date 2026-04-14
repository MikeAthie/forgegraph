# Database Recovery

## Production source of truth

Production recovery uses native PostgreSQL backups created by `scripts/ops/backup_postgres.sh` and restored by `scripts/ops/restore_postgres.sh`.

The Django `backup_database` and `restore_database` management commands remain dev/support tools only.

## Restore flow

1. stop traffic or isolate the target environment
2. restore the selected native backup into a fresh database
3. start backend against the restored database
4. run backend readiness and authenticated smoke checks
5. verify stale-run reconciliation and queue state

## Required validation

- `/ready` returns 200
- auth register/login/me flow succeeds
- metrics and run summaries render
- recent run/event records are present

