# Scalability Program

Phase 4 separates capacity evidence from product claims. ForgeGraph can be
designed for high concurrency, but launch claims must match measured results.

## Capacity Tiers

| Tier | Target | Meaning | Claim Status |
| --- | --- | --- | --- |
| Alpha | 5-10 concurrent agents | internal/customer design partners only | allowed after P0/P1 gates |
| Private beta | 25-50 concurrent agents | limited external users | allowed after clean 25/50 evidence |
| Production v1 | 100 concurrent agents | reliable multi-org operation | allowed after clean 100 evidence |
| Production scale | 500+ concurrent agents | proven high-scale company OS | roadmap until measured |

Do not market the 500+ tier until the production-scale evidence package passes.

## Separate Measurements

Capacity reports must measure these paths separately:

- Engine scheduling capacity without LLM calls.
- Backend runtime-intent processing capacity.
- WebSocket fanout capacity.
- LLM provider throughput.
- Queue saturation behavior.
- Cost-accounting overhead.
- Memory-write overhead.

## Required Load Scenarios

The harness in [scripts/stress_runner.py](../../scripts/stress_runner.py) exposes
Phase 4 scenario names:

- `synthetic-no-llm-500`: 500 concurrent output-only runs through the real
  backend, runtime intent worker, engine, Redis/Postgres, and WebSocket path.
- `controlled-llm-latency`: fake/chaos LLM latency with queue size, timeout,
  and max-in-flight controls.
- `real-provider-capacity`: realistic provider/model run with cost tracking,
  memory writes, and WebSocket observers enabled.

For Phase 4 scenarios, `--runs` must be at least the highest requested
concurrency level. Otherwise the harness refuses to run because the result would
not exercise the claimed concurrency.

Example synthetic gate:

```bash
python scripts/stress_runner.py \
  --base-url http://localhost:8000 \
  --email admin@example.com \
  --password admin-password \
  --metrics-email admin@example.com \
  --metrics-password admin-password \
  --graph-version-id 00000000-0000-0000-0000-000000000000 \
  --scenario synthetic-no-llm-500 \
  --runs 500
```

Example controlled LLM backpressure gate:

```bash
python scripts/stress_runner.py \
  --base-url http://localhost:8000 \
  --email admin@example.com \
  --password admin-password \
  --metrics-email admin@example.com \
  --metrics-password admin-password \
  --graph-version-id 00000000-0000-0000-0000-000000000000 \
  --scenario controlled-llm-latency \
  --capacity-tier private-beta \
  --llm-mock-delay-ms 1500 \
  --llm-mock-max-in-flight 4 \
  --llm-max-queue-size 32 \
  --llm-queue-timeout-ms 5000 \
  --runs 50 \
  --allow-service-disruption
```

Example real provider gate:

```bash
python scripts/stress_runner.py \
  --base-url http://localhost:8000 \
  --email admin@example.com \
  --password admin-password \
  --metrics-email admin@example.com \
  --metrics-password admin-password \
  --graph-version-id 00000000-0000-0000-0000-000000000000 \
  --scenario real-provider-capacity \
  --capacity-tier alpha \
  --runs 10 \
  --allow-real-provider
```

## Production v1 Acceptance

Before broad production, the evidence package must show:

- 100 concurrent agents.
- No backend stalls.
- No silent task loss.
- Bounded queue depth.
- p95 backend API latency within target.
- p95 WebSocket send/delivery latency within target.
- No manual restart after the load test.
- Dead-letter rate understood and visible.

The CI `load-smoke` job remains a 100-run no-LLM regression gate. It is not a
production capacity claim by itself.

## WebSocket Hardening

Run WebSockets must remain backend-state-first:

- Per-org and per-user connection limits are enforced before connection accept.
- Event-level and event-type filters reduce fanout pressure.
- Heartbeats and client `pong` messages update subscriber activity.
- Slow clients are disconnected after bounded send timeout.
- Subscriber snapshots expose per-org connections, fanout counts, filtered
  events, dropped messages, and slow disconnects.
- Reconnects use `last_event_id` as a hint and receive a `resync_required`
  signal; clients refetch backend state rather than trusting replayed transport
  events as authoritative state.

A slow browser tab must not degrade other users or organizations.
