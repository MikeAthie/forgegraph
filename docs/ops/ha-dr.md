# High Availability + Disaster Recovery

## RPO/RTO Targets (Default)
- RPO: 24 hours
- RTO: 4 hours

## Backup Strategy
- Database backups via `python manage.py backup_database`.
- Schedule backups at least once per day (cron, systemd timer, or orchestrator job).
- Store backups in encrypted object storage with lifecycle rules.

## Restore Procedure
1. Provision a clean database instance.
2. Run `python manage.py migrate`.
3. Restore data with `python manage.py restore_database --input /path/to/backup.json`.
4. Verify core workflows (auth, run creation, run execution).

## Health Checks
- API health: `GET /api/health/`
- Engine health: `GET /api/health/engine`
- Metrics: `GET /api/metrics/summary` (admin-only)

## Validation
- Run a monthly restore drill into staging.
- Record the restore time and compare against RTO.
