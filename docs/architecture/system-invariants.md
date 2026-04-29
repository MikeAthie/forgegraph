# System Invariants

> Internal terminology notice: These terms are INTERNAL and not user-facing. Product surfaces must translate them through the canonical ontology and frontend domain ViewModels.

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is the canonical runtime contract.
> This document is broader system guidance. If it conflicts with runtime behavior, `runtime-invariants.md` wins.

These rules describe broader product and platform guidance around the runtime contract.

## Core Direction

- ForgeGraph is a programmable company OS with an autonomous runtime and human oversight.
- The architectural pattern is:
  `Command -> Execute -> Emit Events -> Materialize State -> Notify UI`

## Single Source Of Truth

- The backend is the source of truth for durable business state.
- The engine is authoritative only for in-flight execution, not persisted system state.
- The frontend never trusts engine state directly.

## System Style

- ForgeGraph is event-driven by default.
- The backend ingests engine events and materializes canonical state.
- The frontend reads backend-owned state through stable APIs and subscriptions.
- The engine should converge toward a stateless runtime.

## Transport Boundaries

- `frontend <-> backend`: REST for standard commands and queries, WebSockets for live updates.
- `backend <-> engine`: gRPC.
- `backend <-> storage`: Postgres, pgvector, Redis.

## Engine Philosophy

- The engine executes work concurrently and emits lifecycle events and results.
- The engine does not own durable task state.
- The engine does not own durable memory.
- The engine does not stay paused waiting for human decisions.

## Human In The Loop

- "Pause" means the backend stores a resumable snapshot and marks the run as awaiting decision.
- Approval or rejection is a backend state transition.
- Resume happens when the backend invokes the engine again with snapshot-backed context.
- No long-lived paused engine process should be required.

## Memory Ownership

- Canonical memory persistence is backend-owned.
- The engine may emit memory-related events or proposals.
- The backend decides what is committed to Postgres and pgvector.

## Memory Model

- Use append-first, mutable-through-derivation.
- `memory_event` is immutable history.
- `memory_item` is the current curated or active representation derived from events.
- History should not be silently overwritten.

## LLM Execution Split

- The backend owns configuration, policy, templates, credentials, quotas, and resolved execution contracts.
- The engine performs the actual model call and tool execution from backend-prepared inputs.
- The engine returns structured outputs and events.
- The backend records durable cost, state, and memory effects.

## Cost Model

- Real-time cost display is optional.
- Budget-breach and limit-breach signaling is required on fast paths.
- Normal cost aggregation may be eventually consistent.

## Frontend Real Time

- WebSockets are the preferred live-update channel.
- Use them for agent activity, run or task status, inbox and approval notifications, alerts, and summary-level log streaming.
- Prefer summaries over raw firehose delivery by default.

## Scale Target

- Design for 500+ agents and high concurrency even if early deployments are smaller.
- Every proposal should be checked against fan-out pressure, WebSocket scaling, event volume, snapshot storage growth, and aggregation cost.

## Auth And Tenancy

- JWT remains the auth model.
- Redis-backed token revocation or deprecation caches are required.
- Multi-tenancy is soft isolation for now.
- Tenant isolation must still be enforced at every query boundary.

## Abuse Protection

- Both rate limiting and throttling are required.
- Hard limits protect fairness and system health.
- Softer degradation handles burst pressure gracefully.

## Idempotency

- Externally triggered write paths should be idempotent where feasible.
- Event ingestion must be idempotent.
- Approval and resume flows must be idempotent.
- Task dispatch should be idempotent or deduplicated.

## Reliability

- No task should be lost silently.
- Failures must surface as visible state.
- Automatic retry is bounded to 3 attempts unless a later contract overrides it.
- Exhausted failures must remain visible to operators.

## Recovery

- Near-term recovery is snapshot-based resume.
- The backend stores resumable execution snapshots.
- The engine restarts work from explicit snapshot-backed context.
- Snapshot boundaries must remain deterministic and replay-safe.
