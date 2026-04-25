# Stress Harness

`scripts/stress_runner.py` runs controlled load and failure scenarios against the
real ForgeGraph control plane.

## Scenarios

- `endpoint-saturation`
- `engine-concurrency`
- `redis-saturation`
- `llm-degradation-delay`
- `llm-degradation-timeout`
- `llm-degradation-unavailable`
- `failure-injection-engine-stop`
- `failure-injection-redis-stop`

## Example

```bash
python scripts/stress_runner.py \
  --base-url http://localhost:8000 \
  --email admin@example.com \
  --password admin-password \
  --metrics-email admin@example.com \
  --metrics-password admin-password \
  --graph-version-id 00000000-0000-0000-0000-000000000000 \
  --scenario all \
  --concurrency 5 10 20 50 \
  --runs 10 \
  --allow-service-disruption
```

Artifacts are written to `logs/stress/<timestamp>/`.

## Sample Run Log

```json
{
  "scenario": "redis-saturation",
  "concurrency": 20,
  "run_id": "5dd4aa97-cd93-4ef8-9c44-87db27da1d83",
  "start_time": "2026-04-25T19:01:18.317648+00:00",
  "end_time": "2026-04-25T19:01:44.492981+00:00",
  "latency_ms": 26175,
  "status": "failure",
  "error": "run finished with status failed",
  "error_type": "internal",
  "queue_status": "processing",
  "queue_attempts": 1,
  "node_execution_time_ms": 23842,
  "node_retry_count": 1,
  "duplicate_node_execution": false,
  "redis_lag": 14,
  "redis_backlog": 19,
  "queue_backlog_size": 22,
  "recovery_state": "transport_degraded",
  "recovery_reason": "transport_backlog"
}
```

## Sample Analysis

```json
{
  "scenario": "failure-injection-engine-stop",
  "breaking_point": "concurrency 10",
  "first_failure_type": "timeout",
  "system_behavior": "recovers",
  "data_integrity": "safe"
}
```
