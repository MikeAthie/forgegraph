# Scalability Program

Phase 6 proves capacity. It does not create a product claim by itself.

The invariant from `docs/architecture/runtime-invariants.md` still wins:
backend owns durable truth, engine executes, frontend observes and controls.
Load tests are invalid if they rely on frontend-derived state, engine-owned
durable memory, silent event drops, or request-time projection repair.

## 500-Agent Benchmark Definition

The production-scale target is defined in
`docs/perf/500-agent-benchmark.md`. The short version is:

- 500 active agents across at least 25 tenants.
- 20 active runs per tenant.
- p95 backend API latency below 300 ms.
- p95 event ingestion latency below 500 ms.
- p95 projection lag below 2 seconds.
- p95 WebSocket delivery below 1 second.
- zero silent drops.
- dead-letter rate below 0.1%.
- no tenant isolation violations.
- memory, HITL, accounting, retry, reconnect, and duplicate-event paths included.

## Capacity Gates

| Gate | Requirement | Required evidence |
| --- | --- | --- |
| A | 25 concurrent agents, 1 hour | zero silent drops |
| B | 50 concurrent agents, 2 hours | projection lag p95 below 2 seconds |
| C | 100 concurrent agents, 4 hours | retry/dead-letter within SLO |
| D | 250 concurrent agents, 4 hours | WebSocket reconnect storm included |
| E | 500 concurrent agents, 8 hours | multi-tenant, HITL, memory, accounting, retries, LLM throttling, failures |

Gate E must pass three consecutive checked-in reports before any public
500-agent claim is allowed. The CI claim guard in
`scripts/ci/check_capacity_claims.py` blocks unqualified public 500-agent copy
unless the latest Gate E evidence under `docs/ops/capacity/gate-e-*.json`
contains three consecutive passing reports and no newer failure.

## Primary Load Generator

Use `tools/loadgen` for Phase 6 capacity evidence. It writes checked-in gate
reports under `docs/ops/capacity/` and raw artifacts under `logs/loadgen/`.

Gate E example:

```bash
go run ./tools/loadgen \
  --base-url http://localhost:8000 \
  --engine-callback-secret "$ENGINE_CALLBACK_SECRET" \
  --gate E \
  --tenants 25 \
  --agents 500 \
  --runs-per-tenant 20 \
  --with-hitl \
  --with-memory \
  --with-accounting \
  --ws-clients 500 \
  --duplicate-event-storm \
  --reconnect-storm \
  --llm-throttling \
  --engine-restart-hook "./ops/restart-engine.sh" \
  --backend-worker-restart-hook "./ops/restart-backend-worker.sh" \
  --redis-degrade-hook "./ops/redis-degrade.sh" \
  --redis-recover-hook "./ops/redis-recover.sh" \
  --llm-throttle-on-hook "./ops/llm-throttle-on.sh" \
  --llm-throttle-off-hook "./ops/llm-throttle-off.sh" \
  --duration 8h
```

`tools/loadgen` only drives backend APIs, signed engine callbacks, WebSockets,
and operator read APIs. It never writes durable state directly.

## Legacy Stress Harness

`scripts/stress_runner.py` remains available for legacy and regression evidence.
It is not the primary Phase 6 500-agent evidence path.

Use `scripts/stress_runner.py` for Phase 3 evidence. It writes:

- `manifest.json`
- `<scenario>/summary.json`
- `<scenario>/runs.jsonl`
- `phase3-gate-<A-E>.json`
- `phase3-gate-<A-E>.md`

Gate example:

```bash
python scripts/stress_runner.py \
  --base-url http://localhost:8000 \
  --email admin@example.com \
  --password admin-password \
  --metrics-email admin@example.com \
  --metrics-password admin-password \
  --graph-version-id 00000000-0000-0000-0000-000000000000 \
  --scenario endpoint-saturation \
  --capacity-gate A \
  --runs 25
```

Gate E example:

```bash
python scripts/stress_runner.py \
  --base-url http://localhost:8000 \
  --email admin@example.com \
  --password admin-password \
  --metrics-email admin@example.com \
  --metrics-password admin-password \
  --tenant-credentials-file .phase3-tenants.json \
  --graph-version-id 00000000-0000-0000-0000-000000000000 \
  --scenario all \
  --capacity-gate E \
  --runs 500 \
  --allow-service-disruption \
  --engine-callback-secret "$ENGINE_CALLBACK_SECRET"
```

The tenant credentials file accepts either a list or `{ "tenants": [...] }`.
Each entry must include `email` and `password`, and may include
`graph_version_id` when each tenant uses a tenant-local graph fixture.

## Required Scenario Coverage

The harness supports these capacity and failure scenarios:

- `endpoint-saturation`
- `engine-concurrency`
- `redis-saturation`
- `llm-degradation-delay`
- `llm-degradation-timeout`
- `llm-degradation-unavailable`
- `failure-injection-engine-stop`
- `failure-injection-redis-stop`
- `websocket-reconnect-storm`
- `duplicate-event-storm`
- `synthetic-no-llm-500`
- `controlled-llm-latency`
- `real-provider-capacity`

Feature flags add per-run stress metadata and post-run checks:

- `--simulate-decisions`
- `--simulate-memory-writes`
- `--simulate-accounting`
- `--simulate-retries`
- `--simulate-ws-reconnects`
- `--simulate-duplicate-events`

Gate D automatically requires WebSocket reconnect evidence. Gate E
automatically requires multi-tenant, HITL, memory, accounting, retry,
LLM throttling, failure injection, WebSocket reconnect, and duplicate-event
evidence. Gate C also requires retry evidence.

## Bottleneck Removal Order

Do not run scale gates against request-time projection repair or engine-owned
product memory. The required order is:

1. Projection workers off request paths.
2. Runtime streams partitioned and bounded by tenant/run where needed.
3. Worker concurrency limits and queue backpressure visible in metrics.
4. DB indexes validated on event ingestion and projection paths.
5. Per-tenant fairness enforced.
6. LLM provider quotas, retry budgets, circuit breakers, and degraded mode set.
7. Phase 3 gates A through E run in order.

## Claim Policy

Allowed before Gate E:

> ForgeGraph is in controlled beta with measured capacity gates in progress.

Not allowed before three passing Gate E reports:

> Run your entire company with 500+ concurrent agents.

Evidence beats intent. Product copy must follow the latest checked-in gate
reports, not architecture goals.
