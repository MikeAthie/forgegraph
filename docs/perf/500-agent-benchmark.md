# 500-Agent Benchmark

This benchmark is Phase 6 evidence, not a product-claim upgrade.

`docs/architecture/runtime-invariants.md` is authoritative. The load generator may drive backend APIs, signed engine callbacks, WebSockets, and operator read APIs, but it must not write durable state directly or treat client or engine state as truth.

## Target

- 500 active agents.
- At least 25 tenants.
- 20 active runs per tenant.
- HITL included.
- Memory writes included.
- Accounting writes included.
- Organization WebSocket clients included.
- Duplicate-event storm included.
- Engine restart included through an explicit external hook.
- Backend worker restart included through an explicit external hook.
- Redis degradation and recovery included through explicit external hooks.
- LLM throttling included through explicit external hooks.

## SLOs

| Metric | Target |
| --- | --- |
| p95 backend API latency | < 300 ms |
| p95 event ingestion latency | < 500 ms |
| p95 projection lag | < 2 seconds |
| p95 WebSocket update latency | < 1 second |
| Dead-letter rate | < 0.1% |
| Silent drop count | 0 |
| Tenant isolation violations | 0 |
| Cost double-counting | 0 |

Silent drop means a generated backend mutation or signed callback was accepted but did not become visible through backend-owned read models or dead-letter records before the observation deadline.

## Primary Harness

Use the Go load generator from the repository root:

```bash
go run ./tools/loadgen \
  --base-url http://127.0.0.1:8000 \
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

Disruption hooks are environment-specific. The harness never guesses Docker, Kubernetes, or cloud commands. Gate E fails if the required hook evidence is missing.

## Evidence Output

For `--gate`, the harness writes checked-in capacity reports:

- `docs/ops/capacity/gate-a-YYYY-MM-DD.json`
- `docs/ops/capacity/gate-a-YYYY-MM-DD.md`
- `docs/ops/capacity/gate-e-YYYY-MM-DD.json`
- `docs/ops/capacity/gate-e-YYYY-MM-DD.md`

Raw supporting artifacts are written under `logs/loadgen/<timestamp>/`:

- `requests.jsonl`
- `runs.jsonl`
- `ws-events.jsonl`
- `hook-timeline.jsonl`
- `metrics-summary.json`
- `tenant-manifest.json`

The harness does not update README or marketing copy automatically.

## Capacity Gates

| Gate | Target | Required result |
| --- | --- | --- |
| A | 25 agents | zero silent drops |
| B | 50 agents | projection lag < 2 seconds |
| C | 100 agents | HITL, memory, and accounting stable |
| D | 250 agents | reconnect storm stable |
| E | 500 agents | 8 hours, 3 consecutive passes |

Gate E must pass three consecutive checked-in reports, with no newer Gate E failure, before public 500-agent claims are allowed.

## Dry Run

Use dry run to validate flags, workload distribution, and report rendering without sending mutations:

```bash
go run ./tools/loadgen \
  --dry-run \
  --tenants 2 \
  --agents 4 \
  --runs-per-tenant 2 \
  --with-memory \
  --with-accounting \
  --ws-clients 4 \
  --duration 2m
```
