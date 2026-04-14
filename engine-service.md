# Engine Service

> Runtime precedence: [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md) is canonical.

The engine is the ForgeGraph execution plane.

## Scope

- Execute workflow revisions concurrently
- Enforce runtime correctness for scheduling, retries, dependencies, and failure visibility
- Emit execution lifecycle events and results to the backend boundary
- Stay stateless with respect to durable business state
- Resume work only from backend-supplied snapshot or execution context

## Design Rules

- Do not own durable task state
- Do not own durable memory state
- Do not stay paused waiting for human approval
- Treat backend-issued execution contracts as the policy and configuration source of truth
- Send durable run-state mutations through backend-controlled runtime write APIs
- Prefer deterministic, invariant-based runtime testing over timing-based assertions

Default runtime state mode is `control-plane-http`. Legacy `dual-write` mode is removed from the supported engine runtime.

## Non-Goals

- Agent registry ownership
- Organization dashboards
- Cost summaries
- Decision center policy
- Product-level system state
- Canonical memory persistence
- Durable approval state

Those belong in the backend control plane and its projections.
