# Engine Service

> Runtime precedence: [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md) is canonical.

The engine is the ForgeGraph execution plane.

## Scope

- Execute backend-issued workflow revision contracts.
- Run nodes, branches, tool calls, retries, and execution-local scheduling.
- Emit signed callbacks, results, metrics, and observability events to backend-owned boundaries.
- Hold only ephemeral in-memory execution state.
- Resume work only from backend-provided snapshot or execution context.

## Design Rules

- Do not own durable run, task, approval, memory, cost, company, or product state.
- Do not remain durably paused waiting for human approval.
- Do not treat Redis, local files, event streams, or process memory as authoritative state.
- Treat backend-issued execution contracts as the policy and configuration source.
- Send durable mutation requests through backend-controlled runtime write APIs.
- Fail closed when backend write or callback boundaries are unavailable.

Default runtime state mode is `control-plane-http`. Legacy `dual-write` mode is removed from the supported engine runtime.

## Non-Goals

- Agent registry ownership
- Organization dashboards
- Company status ownership
- Cost summaries
- Decision center policy
- Product-level system state
- Canonical memory persistence
- Durable approval state

Those belong in the backend control plane and backend-owned projections.

## Testing Guidance

Engine tests should verify execution behavior, callback boundaries, statelessness guardrails, retries, cancellation, and metrics. They should not assert durable business-state ownership inside the engine.
