# Control Plane vs Execution Plane Contract

## Purpose
Define the responsibilities and failure semantics between the Forgegraph control plane (backend) and execution plane (engine). This is a semantic contract, not an API spec.

## Ownership and Source of Truth
- Control plane owns run lifecycle state in the database (Run, NodeRun, RunEvent).
- Execution plane owns in-flight execution and produces events for state transitions.
- If control plane and engine disagree, the control plane is the source of truth for UI and API responses.

## Responsibilities
### Control Plane (Django/DRF + Channels)
- AuthN/AuthZ and tenant isolation.
- Persistent storage for runs, node runs, events, usage, budgets, and audit logs.
- Normalization of engine events into stable API payloads.
- Replay orchestration and user-visible run history.
- Streaming to clients over WS/SSE.

### Execution Plane (Go Engine)
- Stateless execution of graphs and nodes.
- Emitting execution events with tenant_id, run_id, event_id.
- Retry delivery of events to the control plane with bounded buffering.
- Local checkpointing and pause/resume mechanics.

## Delivery Guarantees
- Event delivery is at-least-once from engine to control plane.
- Control plane enforces idempotency using (run_id, event_id).
- Event ordering is best-effort; control plane applies updates by timestamp.

## Partial Failure Semantics
### If the control plane is down for 10 minutes
- Engine continues executing if it already accepted the run.
- Engine retries event delivery with bounded buffering and backoff.
- If buffering overflows, some events may be dropped; control plane will reconcile run status via `GetRunStatus` and mark missing details as unknown.
- Once the control plane is back, new events continue to stream; earlier gaps may remain until reconciliation.

### If the engine is down
- Control plane marks the run as failed if the engine cannot be reached or a heartbeat fails beyond the timeout.
- No new events are expected; replay requires re-dispatch.

### If WS/SSE is down
- Control plane remains source of truth; clients must reconnect and resume from last event id or timestamp.

## Headless Execution
- Engine can run headless if `callback_url` is empty.
- In headless mode, no real-time updates or persisted run history are available.
- For MVP demo and production runs, `callback_url` is required.

## Replay Semantics Ownership
- Control plane initiates replay and records it as a new run or a replay session.
- Engine executes from checkpointed state but does not mutate historical run records.
- Replay is explicit and auditable.

## Tenant Isolation Contract
- `tenant_id` must be present in every engine event and usage record.
- Control plane verifies tenant ownership on ingestion before persisting.
- Audit logs must include tenant_id for every entry.

## Non-Goals (MVP)
- Guaranteed event backfill after long control plane outages.
- Cross-region active/active run recovery.
- Exactly-once delivery guarantees.
