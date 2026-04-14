# Observability

Operational observability has two layers:

- canonical execution traces for exact runtime behavior
- summary projections and counters for alerting, triage, and operator dashboards

Both layers are required. Summaries accelerate supervision; traces preserve truth.

## Production signals

Backend signals:

- run lifecycle totals by outcome
- stale reconciliation totals by `recovery_reason`
- queue depth and oldest pending age
- WebSocket connection failures and dropped messages
- callback authentication failures
- API request volume, 5xx totals, and latency percentiles

Engine signals:

- `/metrics` Prometheus output
- `/ready` readiness for traffic admission
- event delivery retry/failure counters
- Redis health on `/health/redis`

Operator thresholds:

- `engine_stalled` or `resume_timeout` reconciliations above baseline require investigation
- queue depth above `SLO_QUEUE_MAX_DEPTH` or oldest pending age above one liveness window is actionable
- any sustained callback auth failures indicate secret drift or an attack path
- sustained backend 5xx or readiness failures block production promotion

## Alert-to-action contract

Every alert must point to a concrete runbook. Minimum mappings:

- backend unhealthy -> `docs/ops/runbooks/backend-unhealthy.md`
- engine unhealthy -> `docs/ops/runbooks/engine-unhealthy.md`
- queue backlog -> `docs/ops/runbooks/queue-backlog.md`
- failed resume flow -> `docs/ops/runbooks/resume-failure.md`
- callback auth failure spike -> `docs/ops/runbooks/callback-auth-failures.md`
- restore required -> `docs/ops/database-recovery.md`

## Source of truth

- metrics are for alerting and trend detection
- traces and durable run events remain the forensic source of truth
- alerts may trigger operator action, but the backend remains authoritative for durable runtime state
