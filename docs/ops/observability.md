# Observability + SLOs

## Metrics
- Backend metrics summary: `GET /api/metrics/summary` (admin-only).
- Engine metrics: `/metrics` from the engine service (Prometheus format).

## Suggested Dashboards
- Run success rate (completed vs failed/canceled).
- Run latency p50/p95.
- Queue depth (pending/processing).

## SLO Guidance
- Run success rate >= 99% (rolling 30 days).
- p95 run latency within defined product target.
- Queue backlog cleared within 5 minutes during normal load.

## Alerting
- Trigger alerts when success rate or latency SLOs violate thresholds for 5 minutes.
- Alert on queue depth spikes beyond expected concurrency.
